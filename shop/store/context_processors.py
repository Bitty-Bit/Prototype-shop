def cart_count(request):
    cart = request.session.get("cart", {})
    # Sum the quantities; this is a lightweight count for the badge.
    count = sum(cart.values()) if cart else 0
    return {"cart_count": count}