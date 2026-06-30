from django.shortcuts import render, get_object_or_404, redirect
from django.db import transaction
from .models import Product, Order, OrderItem, CustomType, Colour
from django.contrib.auth import login
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse


def get_cart_data(request):
    """Reads the cart, auto-corrects any quantity that exceeds stock,
    and returns clean items + totals. Saves the cart back if it changed."""
    cart = request.session.get("cart", {})
    changed = False
    items = []
    total_cents = 0
    count = 0

    for product_id, quantity in list(cart.items()):
        product = Product.objects.filter(pk=product_id).first()
        if not product or not product.is_available:
            # Product gone or unavailable — drop it from the cart.
            del cart[product_id]
            changed = True
            continue

        # Cap stock items at what's actually available.
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
        request.session["cart"] = cart  # persist the corrections

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
        # Pull submitted values.
        type_id = request.POST.get("custom_type")
        colour_id = request.POST.get("colour")
        custom_name = request.POST.get("custom_name", "").strip()
        length = request.POST.get("length", "").strip()
        width = request.POST.get("width", "").strip()
        unit = request.POST.get("measurement_unit", "").strip()
        notes = request.POST.get("notes", "").strip()

        # Server-side validation — the real guard (browser 'required' is just a courtesy).
        errors = []
        if not type_id:
            errors.append("Please choose a custom type.")
        if not custom_name:
            errors.append("Please give your custom order a name.")
        if not length or not width:
            errors.append("Please enter both length and width.")
        if not unit:
            errors.append("Please choose a measurement unit.")
        if not colour_id:
            errors.append("Please pick a colour.")

        if not errors:
            # Stash this custom request in the session cart (a list of custom items).
            custom_cart = request.session.get("custom_cart", [])
            custom_cart.append({
                "product_id": product.pk,
                "custom_type_id": type_id,
                "custom_name": custom_name,
                "length": length,
                "width": width,
                "measurement_unit": unit,
                "colour_id": colour_id,
                "notes": notes,
            })
            request.session["custom_cart"] = custom_cart
            request.session.modified = True
            return redirect("cart_detail")

        # Re-show the form with errors and what they typed.
        return render(request, "store/custom_order.html", {
            "product": product, "types": types, "colours": colours,
            "errors": errors, "submitted": request.POST,
        })

    # First visit (GET) — empty form.
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


def checkout(request):
    cart = request.session.get("cart", {})
    if not cart:
        return redirect("cart_detail")

    try:
        # Everything inside this block either fully succeeds or fully undoes
        # itself — no half-finished orders, no stock deducted without an order.
        with transaction.atomic():
            order = Order.objects.create(
                user=request.user if request.user.is_authenticated else None
            )
            total_cents = 0
            has_custom = False

            for product_id, quantity in cart.items():
                # Lock this product's row so two simultaneous checkouts
                # can't both grab the last unit (the "last item" problem).
                product = Product.objects.select_for_update().get(pk=product_id)

                if not product.is_available:
                    # Skip anything that went unavailable since being added.
                    continue

                if product.product_type == "stock":
                    if product.stock_quantity < quantity:
                        # Not enough stock — sell what's left, or skip.
                        quantity = product.stock_quantity
                    if quantity <= 0:
                        continue
                    product.stock_quantity -= quantity   # the deduction
                    product.save()
                else:
                    has_custom = True   # custom items don't deduct stock

                OrderItem.objects.create(
                    order=order,
                    product=product,
                    product_name=product.name,
                    unit_price_cents=product.price_cents,
                    quantity=quantity,
                )
                total_cents += product.price_cents * quantity

            order.total_cents = total_cents
            order.has_custom_items = has_custom
            order.save()
    except Product.DoesNotExist:
        return redirect("cart_detail")

    # Order placed — empty the cart.
    request.session["cart"] = {}
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