from django.urls import path
from carts.views import (
    CartView, AddToCartView, UpdateCartItemView, DeleteCartItemView,
    CheckoutView, PayOrderView, OrderPayStatusView, StripeWebhookView,
    get_all_ordersView, CancelOrderView, ActivenowView, admin_get_all_ordersView,
    AdminUpdateOrderStatusView, VerifyPurchaseView, GetOrderView, AdminGetOrderView
)

urlpatterns = [
    path('cart/', CartView.as_view(), name='cart-detail'),
    path('cart/add/', AddToCartView.as_view(), name='cart-add'),
    path('cart/item/<int:item_id>/update/', UpdateCartItemView.as_view(), name='cart-item-update'),
    path('cart/item/<int:item_id>/delete/', DeleteCartItemView.as_view(), name='cart-item-delete'),
    path('checkout/', CheckoutView.as_view(), name='checkout'),
    path('order/<int:order_id>/', GetOrderView.as_view(), name='get-order'),
    path('order/<int:order_id>/pay/', PayOrderView.as_view(), name='pay-order'),
    path('order/<int:order_id>/pay/status/', OrderPayStatusView.as_view(), name='order-pay-status'),
    path('stripe/webhook/', StripeWebhookView.as_view(), name='stripe-webhook'),
    path('order/<int:order_id>/cancel/', CancelOrderView.as_view(), name='cancel-order'),
    path('get-all-orders/', get_all_ordersView.as_view(), name='get-all-orders'),
    path('admin-get-all-orders/', admin_get_all_ordersView.as_view(), name='admin-get-all-orders'),
    path('admin-orders/<int:order_id>/', AdminGetOrderView.as_view(), name='admin-get-order'),
    path('admin-orders/<int:order_id>/status/', AdminUpdateOrderStatusView.as_view(), name='admin-update-order-status'),
    path('verify-purchase/<int:user_id>/<int:product_id>/', VerifyPurchaseView.as_view(), name='verify-purchase'),
    path('active/', ActivenowView.as_view(), name='active'),

]
