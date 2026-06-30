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


// Custom-order colour picker: limit to 5, update the counter live.
document.addEventListener("change", function (event) {
    if (!event.target.classList.contains("swatch-check")) return;

    const checks = document.querySelectorAll(".swatch-check");
    const chosen = document.querySelectorAll(".swatch-check:checked").length;

    // Update the counter text.
    const counter = document.getElementById("colour-count");
    if (counter) counter.textContent = chosen;

    // If 5 are picked, disable the unchecked ones; otherwise re-enable all.
    checks.forEach((box) => {
        box.disabled = (chosen >= 5 && !box.checked);
        box.closest(".swatch").classList.toggle("swatch-disabled", box.disabled);
    });
});


// Order details modal — fetch and show without leaving the page.
document.addEventListener("click", function (event) {
    const row = event.target.closest(".js-order");
    if (row) {
        event.preventDefault();
        const id = row.dataset.order;
        fetch(`/order/${id}/json/`)
            .then((r) => r.json())
            .then((order) => renderOrderModal(order))
            .catch(() => {});
        return;
    }
    // Close handlers
    if (event.target.id === "modal-close" || event.target.id === "order-modal") {
        document.getElementById("order-modal").classList.remove("open");
    }
});

function renderOrderModal(order) {
    let html = `<h2 class="modal-title">Order #${order.id}</h2>`;
    html += `<p class="modal-meta">${order.status} · ${order.created} · ${order.total}</p>`;
    order.items.forEach((item) => {
        html += `<div class="modal-item"><strong>${item.quantity} × ${item.name}</strong> — ${item.line_total}`;
        if (item.is_custom) {
            html += `<div class="modal-spec">`;
            if (item.size) html += `<div>Size: ${item.size}</div>`;
            if (item.colours.length) {
                html += `<div>Colours: `;
                item.colours.forEach((c) => {
                    html += `<span class="mini-swatch" style="background:${c.hex}" title="${c.name}"></span>`;
                });
                html += `</div>`;
            }
            if (item.notes) html += `<div>Notes: ${item.notes}</div>`;
            if (item.images.length) {
                html += `<div class="modal-images">`;
                item.images.forEach((url) => {
                    html += `<img src="${url}" alt="reference">`;
                });
                html += `</div>`;
            }
            html += `</div>`;
        }
        html += `</div>`;
    });
    document.getElementById("modal-body").innerHTML = html;
    document.getElementById("order-modal").classList.add("open");
}