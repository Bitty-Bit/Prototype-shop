from django.urls import path
from . import views

urlpatterns = [
    path("", views.product_list, name="product_list"),
    path("product/<int:pk>/", views.product_detail, name="product_detail"),
    path("cart/", views.cart_detail, name="cart_detail"),
    path("cart/add/<int:pk>/", views.add_to_cart, name="add_to_cart"),
    path("cart/remove/<int:pk>/", views.remove_from_cart, name="remove_from_cart"),
    path("checkout/", views.checkout, name="checkout"),
    path("signup/", views.signup, name="signup"),
    path("account/", views.account, name="account"),
    path("order/<int:pk>/", views.order_detail, name="order_detail"),
    path("cart/remove-all/<int:pk>/", views.remove_all_from_cart, name="remove_all_from_cart"),
    path("cart/remove-custom/<int:index>/", views.remove_custom_item, name="remove_custom_item"),
    path("order/<int:pk>/json/", views.order_detail_json, name="order_detail_json"),
]