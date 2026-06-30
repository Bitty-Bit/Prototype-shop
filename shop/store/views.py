from django.shortcuts import render, get_object_or_404, redirect
from django.db import transaction
from .models import Product, Order, OrderItem, CustomType, Colour
from django.contrib.auth import login
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.contrib import messages
from .models import CustomOrderImage
from PIL import Image
import io
from django.core.files.base import ContentFile

def get_cart_data(request):
    """Builds the combined cart: normal stock items + custom items,
    with totals and a count. Auto-corrects stock quantities."""
    cart = request.session.get("cart", {})
    custom_cart = request.session.get("custom_cart", [])
    changed = False
    items = []
    custom_items = []
    total_cents = 0
    count = 0

    # --- Normal stock/products ---
    for product_id, quantity in list(cart.items()):
        product = Product.objects.filter(pk=product_id).first()
        if not product or not product.is_available:
            del cart[product_id]
            changed = True
            continue
        if product.product_type == "stock" and quantity > product.stock_quantity:
            quantity = product.stock_quantity
            cart[product_id] = quantity
            changed = True
        if quantity <= 0:
            del cart[product_id]
            changed = True
            continue
        line_cents = product.price_cents * quantity
        total_cents += line_cents
        count += quantity
        items.append({
            "product": product,
            "quantity": quantity,
            "line_total": f"{product.currency} {line_cents / 100:.2f}",
        })

    if changed:
        request.session["cart"] = cart

    # --- Custom items ---
    for index, entry in enumerate(custom_cart):
        ctype = CustomType.objects.filter(pk=entry.get("custom_type_id")).first()
        if not ctype:
            continue
        entry_colours = Colour.objects.filter(pk__in=entry.get("colour_ids", []))
        line_cents = ctype.price_cents
        total_cents += line_cents
        count += 1
        custom_items.append({
            "index": index,                       # position in custom_cart (for removal)
            "name": entry.get("custom_name"),
            "type": ctype,
            "length": entry.get("length"),
            "width": entry.get("width"),
            "unit": entry.get("measurement_unit"),
            "colours": entry_colours,
            "notes": entry.get("notes"),
            "line_total": ctype.price_display,    # shows "Negotiable" for Other
            "price_cents": line_cents,
        })

    return {
        "items": items,
        "custom_items": custom_items,
        "total": f"ZAR {total_cents / 100:.2f}",
        "count": count,
    }

    return {
        "items": items,
        "total": f"ZAR {total_cents / 100:.2f}",
        "count": count,
    }

def product_list(request):
    products = Product.objects.all().order_by("-is_pinned", "-created_at")
    return render(request, "store/product_list.html", {"products": products})

def product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk)

    # Custom-order product gets its own request form.
    if product.is_custom_order:
        return custom_order_form(request, product)

    return render(request, "store/product_detail.html", {"product": product})


def custom_order_form(request, product):
    types = CustomType.objects.filter(is_active=True)
    colours = Colour.objects.filter(is_active=True)

    if request.method == "POST":
        type_id = request.POST.get("custom_type")
        colour_ids = request.POST.getlist("colours")   # getlist — multiple values
        custom_name = request.POST.get("custom_name", "").strip()
        length = request.POST.get("length", "").strip()
        width = request.POST.get("width", "").strip()
        unit = request.POST.get("measurement_unit", "").strip()
        notes = request.POST.get("notes", "").strip()

        # Server-side validation — the real guard.
        errors = []
        if not type_id:
            errors.append("Please choose a custom type.")
        if not custom_name:
            errors.append("Please give your custom order a name.")
        if not length or not width:
            errors.append("Please enter both length and width.")
        if not unit:
            errors.append("Please choose a measurement unit.")
        if len(colour_ids) < 1:
            errors.append("Please pick at least one colour.")
        if len(colour_ids) > 5:
            errors.append("You can pick a maximum of 5 colours.")

        if not errors:
            custom_cart = request.session.get("custom_cart", [])
            custom_cart.append({
                "product_id": product.pk,
                "custom_type_id": type_id,
                "custom_name": custom_name,
                "length": length,
                "width": width,
                "measurement_unit": unit,
                "colour_ids": colour_ids,   # now a list
                "notes": notes,
            })
            request.session["custom_cart"] = custom_cart
            request.session.modified = True
            return redirect("cart_detail")

        return render(request, "store/custom_order.html", {
            "product": product, "types": types, "colours": colours,
            "errors": errors, "submitted": request.POST,
        })

    return render(request, "store/custom_order.html", {
        "product": product, "types": types, "colours": colours,
        "submitted": {},
    })

def add_to_cart(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if not product.is_available:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"ok": False, "error": "unavailable"}, status=400)
        return redirect("product_detail", pk=pk)

    cart = request.session.get("cart", {})
    product_id = str(pk)
    current_qty = cart.get(product_id, 0)

    # For stock items, never let the cart exceed available stock.
    at_limit = (product.product_type == "stock" and current_qty >= product.stock_quantity)
    if not at_limit:
        cart[product_id] = current_qty + 1
        request.session["cart"] = cart

    count = sum(cart.values())

    # If this was an AJAX (background) request, reply with JSON instead of redirecting.
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"ok": True, "count": count, "at_limit": at_limit})

    # Otherwise behave the old way (fallback if JS is off).
    return redirect("cart_detail")

def cart_detail(request):
    data = get_cart_data(request)
    return render(request, "store/cart.html", {
        "items": data["items"],
        "custom_items": data["custom_items"],
        "total": data["total"],
    })


def remove_from_cart(request, pk):
    cart = request.session.get("cart", {})
    product_id = str(pk)
    if product_id in cart:
        cart[product_id] -= 1          # drop by one
        if cart[product_id] <= 0:      # gone entirely once it hits zero
            del cart[product_id]
        request.session["cart"] = cart
    return redirect("cart_detail")

def remove_all_from_cart(request, pk):
    cart = request.session.get("cart", {})
    product_id = str(pk)
    if product_id in cart:
        del cart[product_id]
        request.session["cart"] = cart
    return redirect("cart_detail")


MAX_IMAGE_BYTES = 10 * 1024 * 1024   # 10 MB cap per file
RESIZE_MAX_EDGE = 2200               # longest edge after resize (keeps detail)


def process_image(uploaded_file):
    """Resize (if large) and compress an uploaded image, preserving quality.
    Returns a Django-ready file, or None if it isn't a valid image."""
    try:
        img = Image.open(uploaded_file)
        img.load()
    except Exception:
        return None

    # Convert modes that can't be saved as JPEG (e.g. PNG transparency).
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    # Resize only if larger than the cap — never upscale.
    if max(img.size) > RESIZE_MAX_EDGE:
        img.thumbnail((RESIZE_MAX_EDGE, RESIZE_MAX_EDGE))  # keeps aspect ratio

    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=90, optimize=True)  # high quality
    buffer.seek(0)
    return ContentFile(buffer.read())


def checkout(request):
    data = get_cart_data(request)
    if not data["items"] and not data["custom_items"]:
        return redirect("cart_detail")

    custom_items = data["custom_items"]

    # If there are NO custom items, place the order immediately (old behaviour).
    if not custom_items:
        return place_order(request, data, images_by_index={})

    # There ARE custom items — they need images.
    if request.method == "POST":
        errors = []
        images_by_index = {}

        for item in custom_items:
            idx = item["index"]
            ctype = item["type"]
            files = request.FILES.getlist(f"images_{idx}")

            # Enforce the per-type count rules.
            if len(files) < ctype.min_images:
                errors.append(f"'{item['name']}' needs at least {ctype.min_images} image(s).")
            if len(files) > ctype.max_images:
                errors.append(f"'{item['name']}' allows at most {ctype.max_images} image(s).")

            processed = []
            for f in files:
                if f.size > MAX_IMAGE_BYTES:
                    errors.append(f"'{f.name}' is over 10 MB.")
                    continue
                result = process_image(f)
                if result is None:
                    errors.append(f"'{f.name}' isn't a valid image.")
                    continue
                processed.append((f.name, result))
            images_by_index[idx] = processed

        if errors:
            return render(request, "store/checkout_upload.html", {
                "custom_items": custom_items, "errors": errors,
            })

        return place_order(request, data, images_by_index=images_by_index)

    # GET — show the upload page.
    return render(request, "store/checkout_upload.html", {
        "custom_items": custom_items,
    })

def place_order(request, data, images_by_index):
    cart = request.session.get("cart", {})
    custom_cart = request.session.get("custom_cart", [])

    try:
        with transaction.atomic():
            order = Order.objects.create(
                user=request.user if request.user.is_authenticated else None
            )
            total_cents = 0
            has_custom = False

            # --- Stock items (with the safe deduction) ---
            for product_id, quantity in cart.items():
                product = Product.objects.select_for_update().get(pk=product_id)
                if not product.is_available:
                    continue
                if product.product_type == "stock":
                    if product.stock_quantity < quantity:
                        quantity = product.stock_quantity
                    if quantity <= 0:
                        continue
                    product.stock_quantity -= quantity
                    product.save()
                OrderItem.objects.create(
                    order=order, product=product,
                    product_name=product.name,
                    unit_price_cents=product.price_cents,
                    quantity=quantity,
                )
                total_cents += product.price_cents * quantity

            # --- Custom items ---
            for index, entry in enumerate(custom_cart):
                ctype = CustomType.objects.filter(pk=entry.get("custom_type_id")).first()
                product = Product.objects.filter(pk=entry.get("product_id")).first()
                if not ctype or not product:
                    continue
                has_custom = True

                item = OrderItem.objects.create(
                    order=order, product=product,
                    product_name=f"{product.name} — {entry.get('custom_name')}",
                    unit_price_cents=ctype.price_cents,
                    quantity=1,
                    custom_type=ctype,
                    custom_name=entry.get("custom_name"),
                    length=entry.get("length") or None,
                    width=entry.get("width") or None,
                    measurement_unit=entry.get("measurement_unit", ""),
                    notes=entry.get("notes", ""),
                )
                # Attach the chosen colours (many-to-many).
                item.colours.set(Colour.objects.filter(pk__in=entry.get("colour_ids", [])))

                # Save the processed images for this item.
                for fname, content in images_by_index.get(index, []):
                    img = CustomOrderImage(order_item=item)
                    img.image.save(fname, content, save=True)

                total_cents += ctype.price_cents

            order.total_cents = total_cents
            order.has_custom_items = has_custom
            order.save()
    except Product.DoesNotExist:
        return redirect("cart_detail")

    # Clear both carts.
    request.session["cart"] = {}
    request.session["custom_cart"] = []
    request.session.modified = True
    return render(request, "store/order_confirmation.html", {"order": order})


def signup(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)  # log them in straight after signing up
            return redirect("product_list")
    else:
        form = UserCreationForm()
    return render(request, "store/signup.html", {"form": form})


@login_required
def account(request):
    orders = request.user.orders.order_by("-created_at")
    return render(request, "store/account.html", {"orders": orders})

@login_required
def order_detail(request, pk):
    # Customers can only view their own orders.
    order = get_object_or_404(Order, pk=pk, user=request.user)
    return render(request, "store/order_detail.html", {"order": order})

def remove_custom_item(request, index):
    custom_cart = request.session.get("custom_cart", [])
    if 0 <= index < len(custom_cart):
        custom_cart.pop(index)
        request.session["custom_cart"] = custom_cart
        request.session.modified = True
    return redirect("cart_detail")


@login_required
def order_detail_json(request, pk):
    order = get_object_or_404(Order, pk=pk, user=request.user)
    items = []
    for item in order.items.all():
        items.append({
            "name": item.product_name,
            "quantity": item.quantity,
            "line_total": item.line_total_display,
            "is_custom": bool(item.custom_type_id),
            "type": item.custom_type.name if item.custom_type else "",
            "size": item.size_display,
            "colours": [{"name": c.name, "hex": c.hex_value} for c in item.colours.all()],
            "notes": item.notes,
            "images": [img.image.url for img in item.images.all()],
        })
    return JsonResponse({
        "id": order.pk,
        "status": order.get_status_display(),
        "total": order.total_display,
        "created": order.created_at.strftime("%d %b %Y") if hasattr(order.created_at, "strftime") else "",
        "items": items,
    })