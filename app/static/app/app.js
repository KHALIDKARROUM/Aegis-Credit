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

    const threshold = document.querySelector('input[name="threshold"]');
    const output = threshold?.parentElement?.querySelector("output");
    if (threshold && output) {
        threshold.addEventListener("input", () => {
            output.value = Number(threshold.value).toFixed(2);
        });
    }
});
