document.addEventListener("DOMContentLoaded", () => {
    for (const group of document.querySelectorAll(".field-group")) {
        const control = group.querySelector("input:not([type='hidden']), select, textarea");
        if (!control) {
            continue;
        }
        const descriptions = Array.from(group.querySelectorAll(".field-hint[id], .field-error[id]"));
        const describedBy = new Set((control.getAttribute("aria-describedby") || "").split(/\s+/).filter(Boolean));
        for (const description of descriptions) {
            describedBy.add(description.id);
        }
        if (describedBy.size) {
            control.setAttribute("aria-describedby", Array.from(describedBy).join(" "));
        }
        if (group.querySelector(".field-error")) {
            control.setAttribute("aria-invalid", "true");
        }
    }

    for (const form of document.querySelectorAll("[data-loading-form]")) {
        form.addEventListener("submit", () => {
            if (!form.checkValidity()) {
                return;
            }
            const button = form.querySelector('button[type="submit"]');
            if (button) {
                button.classList.add("is-loading");
                button.setAttribute("aria-busy", "true");
                button.setAttribute("aria-label", button.dataset.loadingLabel || "Processing request");
                button.disabled = true;
            }
        });
    }

    for (const slider of document.querySelectorAll("[data-threshold-slider]")) {
        const output = document.getElementById(slider.getAttribute("aria-controls"));
        if (!output) {
            continue;
        }
        const updateOutput = () => {
            output.value = Number(slider.value).toFixed(2);
            output.textContent = output.value;
        };
        slider.addEventListener("input", updateOutput);
        updateOutput();
    }

    for (const button of document.querySelectorAll("[data-print-button]")) {
        button.addEventListener("click", () => window.print());
    }
});
