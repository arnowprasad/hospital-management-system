document.addEventListener("DOMContentLoaded", () => {
    const navToggle = document.querySelector(".nav-toggle");
    const siteNav = document.querySelector(".site-nav");

    if (navToggle && siteNav) {
        navToggle.addEventListener("click", () => {
            siteNav.classList.toggle("open");
        });
    }

    const flashMessages = document.querySelectorAll(".flash-message");
    flashMessages.forEach((message) => {
        setTimeout(() => {
            message.style.opacity = "0";
            message.style.transform = "translateY(-6px)";
            message.style.transition = "all 0.3s ease";
            setTimeout(() => message.remove(), 300);
        }, 3500);
    });
});
