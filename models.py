from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()


class Doctor(db.Model):
    """Doctor model stores doctor login and profile details."""

    __tablename__ = "doctors"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    specialty = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    appointments = db.relationship("Appointment", back_populates="doctor", lazy=True)


class Patient(db.Model):
    """Patient model stores patient login and contact details."""

    __tablename__ = "patients"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    appointments = db.relationship("Appointment", back_populates="patient", lazy=True)


class Appointment(db.Model):
    """Appointment model links a patient with a doctor and visit details."""

    __tablename__ = "appointments"

    id = db.Column(db.Integer, primary_key=True)
    patient_name = db.Column(db.String(120), nullable=False)
    age = db.Column(db.Integer, nullable=False)
    gender = db.Column(db.String(20), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    appointment_date = db.Column(db.Date, nullable=False)
    appointment_time = db.Column(db.Time, nullable=False)
    problem = db.Column(db.Text, nullable=False)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey("doctors.id"), nullable=False)

    patient = db.relationship("Patient", back_populates="appointments")
    doctor = db.relationship("Doctor", back_populates="appointments")
