// Handle any form with the class "ajax-add" without reloading the page.
document.addEventListener("submit", function (event) {
    const form = event.target;
    if (!form.classList.contains("ajax-add")) return;  // ignore other forms

    event.preventDefault();  // stop the normal page navigation

    fetch(form.action, {
        method: "POST",
        headers: {
            "X-Requested-With": "XMLHttpRequest",  // tells the view "this is AJAX"
            "X-CSRFToken": form.querySelector("[name=csrfmiddlewaretoken]").value,
        },
    })
    .then((response) => response.json())
    .then((data) => {
        if (!data.ok) return;

        // Update the badge number and make sure it's visible.
        const badge = document.getElementById("cart-count");
        if (badge) {
            badge.textContent = data.count;
            badge.style.display = data.count > 0 ? "" : "none";
        }

        // Give the button a brief "Added" confirmation.
        const button = form.querySelector("button");
        if (button) {
            button.classList.add("added");
            setTimeout(() => button.classList.remove("added"), 900);
        }
    })
    .catch(() => { /* if something fails, do nothing — page stays put */ });
});