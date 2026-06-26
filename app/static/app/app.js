document.addEventListener("DOMContentLoaded", () => {
    for (const form of document.querySelectorAll("[data-loading-form]")) {
        form.addEventListener("submit", () => {
            if (!form.checkValidity()) {
                return;
            }
            const button = form.querySelector('button[type="submit"]');
            if (button) {
                button.classList.add("is-loading");
                button.setAttribute("aria-busy", "true");
                button.disabled = true;
            }
        });
    }

});
