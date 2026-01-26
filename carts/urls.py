from django.urls import path
from carts.views import (
    CartView, AddToCartView, UpdateCartItemView, DeleteCartItemView,
    CheckoutView, PayOrderView,get_all_ordersView
)

urlpatterns = [
    path('cart/', CartView.as_view(), name='cart-detail'),
    path('cart/add/', AddToCartView.as_view(), name='cart-add'),
    path('cart/item/<int:item_id>/update/', UpdateCartItemView.as_view(), name='cart-item-update'),
    path('cart/item/<int:item_id>/delete/', DeleteCartItemView.as_view(), name='cart-item-delete'),
    path('checkout/', CheckoutView.as_view(), name='checkout'),
    path('order/<int:order_id>/pay/', PayOrderView.as_view(), name='pay-order'),
    path('get-all-orders/', get_all_ordersView.as_view(), name='get-all-orders'),

]
