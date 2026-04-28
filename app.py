import os
from datetime import date, datetime
from functools import wraps
from urllib.parse import urlencode

import requests
from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from models import Appointment, Doctor, Patient, db


app = Flask(__name__)
app.config["SECRET_KEY"] = "hospital-management-secret-key"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///hospital.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)


def load_env_file():
    """Load simple KEY=VALUE pairs from a local .env file if present."""
    env_path = os.path.join(app.root_path, ".env")
    if not os.path.exists(env_path):
        return

    with open(env_path, encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env_file()


def get_appid_config():
    """Read IBM App ID settings from environment variables."""
    client_id = os.getenv("clientid") or os.getenv("APPID_CLIENT_ID")
    client_secret = os.getenv("clientsecret") or os.getenv("APPID_CLIENT_SECRET")
    redirect_uri = os.getenv("redirecturl") or os.getenv("APPID_REDIRECT_URL")
    tenant_id = os.getenv("tenantid") or os.getenv("APPID_TENANT_ID")
    discovery_url = (
        os.getenv("discoveryurl")
        or os.getenv("dicoveryurl")
        or os.getenv("APPID_DISCOVERY_URL")
    )
    oauth_server_url = os.getenv("oauthserverurl") or os.getenv("APPID_OAUTH_SERVER_URL")

    if not oauth_server_url and discovery_url and tenant_id:
        oauth_server_url = f"{discovery_url.rstrip('/')}/oauth/v4/{tenant_id}"

    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "tenant_id": tenant_id,
        "discovery_url": discovery_url,
        "oauth_server_url": oauth_server_url,
    }


def appid_is_configured():
    config = get_appid_config()
    return all(
        [
            config["client_id"],
            config["client_secret"],
            config["redirect_uri"],
            config["oauth_server_url"],
        ]
    )


def get_oauth_metadata():
    """Fetch the IBM App ID OIDC metadata document."""
    oauth_server_url = get_appid_config()["oauth_server_url"]
    if not oauth_server_url:
        raise ValueError("IBM App ID OAuth server URL is missing.")

    response = requests.get(
        f"{oauth_server_url.rstrip('/')}/.well-known/openid-configuration",
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def get_authorization_url(role):
    metadata = get_oauth_metadata()
    config = get_appid_config()
    state = os.urandom(16).hex()

    session["oauth_state"] = state
    session["oauth_role"] = role

    query = urlencode(
        {
            "client_id": config["client_id"],
            "response_type": "code",
            "redirect_uri": config["redirect_uri"],
            "scope": "openid profile email",
            "state": state,
        }
    )
    return f"{metadata['authorization_endpoint']}?{query}"


def exchange_code_for_tokens(code):
    metadata = get_oauth_metadata()
    config = get_appid_config()
    response = requests.post(
        metadata["token_endpoint"],
        data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
            "redirect_uri": config["redirect_uri"],
        },
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def fetch_userinfo(access_token):
    metadata = get_oauth_metadata()
    response = requests.get(
        metadata["userinfo_endpoint"],
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def sign_in_local_user_from_appid(role, userinfo):
    """Map the App ID email identity to a local patient or doctor record."""
    email = (userinfo.get("email") or "").strip().lower()
    if not email:
        raise ValueError("IBM App ID did not return an email address.")

    session.clear()
    session["oauth_user"] = userinfo
    session["auth_provider"] = "ibm_app_id"
    session["email"] = email
    session["role"] = role

    if role == "patient":
        patient = Patient.query.filter_by(email=email).first()
        if not patient:
            raise LookupError("No patient account matches your IBM App ID email.")
        session["patient_id"] = patient.id
        session["name"] = patient.full_name
        return url_for("index")

    doctor = Doctor.query.filter_by(email=email).first()
    if not doctor:
        raise LookupError("No doctor account matches your IBM App ID email.")
    session["doctor_id"] = doctor.id
    session["name"] = doctor.full_name
    return url_for("doctor_dashboard")

def seed_default_doctors():
    """Add starter doctors so the appointment portal has data to show."""
    if Doctor.query.count() > 0:
        return

    starter_doctors = [
        {
            "full_name": "Arjun Mehta",
            "email": "arjun.mehta@medicarehospital.com",
            "specialty": "Cardiologist",
        },
        {
            "full_name": "Priya Sharma",
            "email": "priya.sharma@medicarehospital.com",
            "specialty": "Pediatrician",
        },
        {
            "full_name": "Rohan Verma",
            "email": "rohan.verma@medicarehospital.com",
            "specialty": "Orthopedic Specialist",
        },
        {
            "full_name": "Neha Kapoor",
            "email": "neha.kapoor@medicarehospital.com",
            "specialty": "Dermatologist",
        },
        {
            "full_name": "Vikram Nair",
            "email": "vikram.nair@medicarehospital.com",
            "specialty": "Neurologist",
        },
        {
            "full_name": "Sana Iqbal",
            "email": "sana.iqbal@medicarehospital.com",
            "specialty": "General Physician",
        },
    ]

    for doctor_data in starter_doctors:
        doctor = Doctor(
            full_name=doctor_data["full_name"],
            email=doctor_data["email"],
            specialty=doctor_data["specialty"],
            password_hash=generate_password_hash("doctor123"),
        )
        db.session.add(doctor)

    db.session.commit()


def login_required(role):
    """Protect routes and allow access only for the expected user role."""

    def decorator(view):
        @wraps(view)
        def wrapped_view(*args, **kwargs):
            if session.get("role") != role:
                flash(f"Please log in as a {role} to continue.", "error")
                if role == "doctor":
                    return redirect(url_for("doctor_login"))
                return redirect(url_for("patient_login"))
            return view(*args, **kwargs)

        return wrapped_view

    return decorator


def validate_appointment_form(form_data):
    """Return a list of validation errors for the appointment form."""
    errors = []
    required_fields = [
        "patient_name",
        "age",
        "gender",
        "phone",
        "doctor_id",
        "date",
        "time",
        "problem",
    ]

    for field in required_fields:
        if not form_data.get(field, "").strip():
            errors.append("All appointment fields are required.")
            break

    age_value = form_data.get("age", "").strip()
    if age_value:
        if not age_value.isdigit() or int(age_value) <= 0 or int(age_value) > 120:
            errors.append("Please enter a valid age between 1 and 120.")

    phone_value = form_data.get("phone", "").strip()
    if phone_value and (not phone_value.isdigit() or len(phone_value) < 10):
        errors.append("Please enter a valid phone number with at least 10 digits.")

    appointment_date = form_data.get("date", "").strip()
    if appointment_date:
        try:
            selected_date = datetime.strptime(appointment_date, "%Y-%m-%d").date()
            if selected_date < date.today():
                errors.append("Appointment date cannot be in the past.")
        except ValueError:
            errors.append("Please select a valid appointment date.")

    appointment_time = form_data.get("time", "").strip()
    if appointment_time:
        try:
            datetime.strptime(appointment_time, "%H:%M")
        except ValueError:
            errors.append("Please select a valid appointment time.")

    return errors


@app.context_processor
def inject_user_context():
    """Share session details across all templates."""
    return {
        "logged_in": "role" in session,
        "current_role": session.get("role"),
        "current_name": session.get("name"),
        "current_patient_id": session.get("patient_id"),
        "auth_provider": session.get("auth_provider"),
        "appid_configured": appid_is_configured(),
    }


@app.route("/")
def index():
    appointments = (
        Appointment.query.order_by(Appointment.appointment_date.asc(), Appointment.appointment_time.asc())
        .all()
    )
    doctors = Doctor.query.order_by(Doctor.full_name.asc()).all()
    return render_template("index.html", appointments=appointments, doctors=doctors)


@app.route("/auth")
def auth_portal():
    return render_template("auth.html")


@app.route("/login/appid/<role>")
def appid_login(role):
    if role not in {"patient", "doctor"}:
        flash("Invalid login role selected.", "error")
        return redirect(url_for("auth_portal"))

    if not appid_is_configured():
        flash("IBM App ID is not configured correctly yet.", "error")
        return redirect(url_for("auth_portal"))

    try:
        return redirect(get_authorization_url(role))
    except requests.RequestException:
        flash("Could not contact IBM App ID. Please check your App ID settings.", "error")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("auth_portal"))


@app.route("/callback")
def appid_callback():
    error = request.args.get("error")
    if error:
        flash(f"IBM App ID login failed: {error}.", "error")
        return redirect(url_for("auth_portal"))

    expected_state = session.get("oauth_state")
    returned_state = request.args.get("state")
    code = request.args.get("code")
    role = session.get("oauth_role")

    if not expected_state or expected_state != returned_state or not code or role not in {"patient", "doctor"}:
        flash("IBM App ID returned an invalid login response.", "error")
        return redirect(url_for("auth_portal"))

    try:
        token_data = exchange_code_for_tokens(code)
        userinfo = fetch_userinfo(token_data["access_token"])
        redirect_target = sign_in_local_user_from_appid(role, userinfo)
        session["auth_provider"] = "ibm_app_id"
        session["id_token"] = token_data.get("id_token")
        session["access_token"] = token_data.get("access_token")
        flash("Logged in with IBM App ID successfully.", "success")
        return redirect(redirect_target)
    except requests.RequestException:
        flash("IBM App ID token exchange failed. Please verify your redirect URL and credentials.", "error")
    except (LookupError, ValueError) as exc:
        flash(str(exc), "error")
    return redirect(url_for("auth_portal"))


@app.route("/patient/register", methods=["GET", "POST"])
def patient_register():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "").strip()

        if not all([full_name, email, phone, password]):
            flash("Please fill in every patient registration field.", "error")
            return redirect(url_for("patient_register"))

        if not phone.isdigit() or len(phone) < 10:
            flash("Please enter a valid phone number.", "error")
            return redirect(url_for("patient_register"))

        existing_patient = Patient.query.filter_by(email=email).first()
        if existing_patient:
            flash("A patient account with this email already exists.", "error")
            return redirect(url_for("patient_register"))

        patient = Patient(
            full_name=full_name,
            email=email,
            phone=phone,
            password_hash=generate_password_hash(password),
        )
        db.session.add(patient)
        db.session.commit()

        flash("Patient registration successful. Please log in.", "success")
        return redirect(url_for("patient_login"))

    return render_template("patient_register.html")


@app.route("/patient/login", methods=["GET", "POST"])
def patient_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()

        patient = Patient.query.filter_by(email=email).first()
        if patient and check_password_hash(patient.password_hash, password):
            session.clear()
            session["role"] = "patient"
            session["patient_id"] = patient.id
            session["name"] = patient.full_name
            flash("Login successful.", "success")
            return redirect(url_for("index"))

        flash("Invalid patient email or password.", "error")
        return redirect(url_for("patient_login"))

    return render_template("patient_login.html")


@app.route("/doctor/register", methods=["GET", "POST"])
def doctor_register():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        specialty = request.form.get("specialty", "").strip()
        password = request.form.get("password", "").strip()

        if not all([full_name, email, specialty, password]):
            flash("Please fill in every doctor registration field.", "error")
            return redirect(url_for("doctor_register"))

        existing_doctor = Doctor.query.filter_by(email=email).first()
        if existing_doctor:
            flash("A doctor account with this email already exists.", "error")
            return redirect(url_for("doctor_register"))

        doctor = Doctor(
            full_name=full_name,
            email=email,
            specialty=specialty,
            password_hash=generate_password_hash(password),
        )
        db.session.add(doctor)
        db.session.commit()

        flash("Doctor registration successful. Please log in.", "success")
        return redirect(url_for("doctor_login"))

    return render_template("doctor_register.html")


@app.route("/doctor/login", methods=["GET", "POST"])
def doctor_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()

        doctor = Doctor.query.filter_by(email=email).first()
        if doctor and check_password_hash(doctor.password_hash, password):
            session.clear()
            session["role"] = "doctor"
            session["doctor_id"] = doctor.id
            session["name"] = doctor.full_name
            flash("Login successful.", "success")
            return redirect(url_for("doctor_dashboard"))

        flash("Invalid doctor email or password.", "error")
        return redirect(url_for("doctor_login"))

    return render_template("doctor_login.html")


@app.route("/book-appointment", methods=["GET", "POST"])
@login_required("patient")
def book_appointment():
    doctors = Doctor.query.order_by(Doctor.full_name.asc()).all()

    if request.method == "POST":
        errors = validate_appointment_form(request.form)
        if errors:
            for error in errors:
                flash(error, "error")
            return redirect(url_for("book_appointment"))

        selected_doctor = db.session.get(Doctor, int(request.form.get("doctor_id")))
        patient = db.session.get(Patient, session.get("patient_id"))

        if not selected_doctor or not patient:
            flash("Unable to create the appointment. Please try again.", "error")
            return redirect(url_for("book_appointment"))

        appointment = Appointment(
            patient_name=request.form.get("patient_name", "").strip(),
            age=int(request.form.get("age")),
            gender=request.form.get("gender", "").strip(),
            phone=request.form.get("phone", "").strip(),
            appointment_date=datetime.strptime(request.form.get("date"), "%Y-%m-%d").date(),
            appointment_time=datetime.strptime(request.form.get("time"), "%H:%M").time(),
            problem=request.form.get("problem", "").strip(),
            patient_id=patient.id,
            doctor_id=selected_doctor.id,
        )
        db.session.add(appointment)
        db.session.commit()

        flash("Appointment booked successfully.", "success")
        return redirect(url_for("index"))

    return render_template("book_appointment.html", doctors=doctors)


@app.route("/doctor/dashboard")
@login_required("doctor")
def doctor_dashboard():
    doctor = db.session.get(Doctor, session.get("doctor_id"))
    appointments = (
        Appointment.query.filter_by(doctor_id=session.get("doctor_id"))
        .order_by(Appointment.appointment_date.asc(), Appointment.appointment_time.asc())
        .all()
    )
    return render_template("doctor_dashboard.html", doctor=doctor, appointments=appointments)


@app.route("/appointment/<int:appointment_id>/cancel", methods=["POST"])
@login_required("patient")
def cancel_appointment(appointment_id):
    appointment = db.session.get(Appointment, appointment_id)

    if not appointment:
        flash("Appointment not found.", "error")
        return redirect(url_for("index"))

    if appointment.patient_id != session.get("patient_id"):
        flash("You can cancel only your own appointments.", "error")
        return redirect(url_for("index"))

    db.session.delete(appointment)
    db.session.commit()
    flash("Appointment cancelled successfully.", "success")
    return redirect(url_for("index"))


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out successfully.", "success")
    return redirect(url_for("index"))


with app.app_context():
    db.create_all()
    seed_default_doctors()


if __name__ == "__main__":
    app.run(debug=True)
