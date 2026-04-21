from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db import transaction
from django.utils import timezone
import uuid
import requests
from rest_framework import serializers
from .models import Cart, CartItem, Order, OrderItem, Transaction, Delivery
from .serializers import CartSerializer, CartItemSerializer, OrderSerializer
from .authentication import MicroserviceJWTAuthentication
from rest_framework.permissions import AllowAny
import stripe
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY

PRODUCT_SERVICE_API = "https://products-k4ov.onrender.com/api/variants/"
BATCH_SERVICE_API = "https://products-k4ov.onrender.com/api/batches/"


# ----------------- Cart -----------------
class CartView(generics.RetrieveAPIView):
    serializer_class = CartSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [MicroserviceJWTAuthentication]

    def get_object(self):
        cart, _ = Cart.objects.get_or_create(user_id=self.request.user.id, is_active=True)
        return cart


class AddToCartView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [MicroserviceJWTAuthentication]

    def post(self, request):
        user = request.user
        cart, _ = Cart.objects.get_or_create(user_id=user.id, is_active=True)

        product_slug = request.data.get('product_slug')
        variant_id = int(request.data.get('variant_id'))
        quantity = int(request.data.get('quantity', 1))
        print(f"variant_id: {variant_id}, product_slug: {product_slug}")

        # --- Step 1: Fetch variant by ID ---
        variant_resp = requests.get(f"{PRODUCT_SERVICE_API}{variant_id}/")
        if variant_resp.status_code != 200:
            return Response({"error": "Variant service unavailable"}, status=503)

        try:
            variant = variant_resp.json()
        except ValueError:
            return Response({"error": "Invalid response from variant service"}, status=502)

        if not variant or 'id' not in variant:
            return Response({"error": "Variant not found"}, status=404)

        # --- Step 2: Fetch product by slug to get product_id ---
        product_resp = requests.get(f"https://products-k4ov.onrender.com/api/products/{product_slug}/")
        if product_resp.status_code != 200:
            return Response({"error": "Product service unavailable"}, status=503)

        try:
            product = product_resp.json()
        except ValueError:
            return Response({"error": "Invalid response from product service"}, status=502)

        product_id = product.get("product_id")
        if not product_id:
            return Response({"error": "Product ID not found"}, status=404)

        # --- Step 3: Create or update cart item ---
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            variant_id=variant['id'],
            defaults={
                'product_id': product_id,              # <-- now correct product_id
                'product_name': product.get('product_name', product_slug),
                'variant_name':variant_id,
                'variant_name': variant.get('name', 'Unknown Variant'),
                'sku': variant.get('sku', ''),
                'price': variant.get('price', 0),
                'quantity': quantity
            }
        )

        if not created:
            cart_item.quantity += quantity
            cart_item.price = variant.get('price', 0)
            cart_item.save()

        # Update cart total
        cart.update_total()

        serializer = CartItemSerializer(cart_item)
        return Response(serializer.data, status=201)






class UpdateCartItemView(generics.UpdateAPIView):
    serializer_class = CartItemSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [MicroserviceJWTAuthentication]
    lookup_url_kwarg = 'item_id'

    def get_queryset(self):
        cart, _ = Cart.objects.get_or_create(user_id=self.request.user.id, is_active=True)
        return CartItem.objects.filter(cart=cart)

    def perform_update(self, serializer):
        serializer.save()
        # update cart total after quantity change
        self.get_queryset().first().cart.update_total()



class DeleteCartItemView(generics.DestroyAPIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [MicroserviceJWTAuthentication]
    lookup_url_kwarg = 'item_id'

    def get_queryset(self):
        cart, _ = Cart.objects.get_or_create(user_id=self.request.user.id, is_active=True)
        return CartItem.objects.filter(cart=cart)

    def perform_destroy(self, instance):
        cart = instance.cart
        instance.delete()
        cart.update_total()



# ----------------- Checkout -----------------
class CheckoutView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [MicroserviceJWTAuthentication]

    @transaction.atomic
    def post(self, request):
        user = request.user
        cart = Cart.objects.get(user_id=user.id, is_active=True)
        cart_items = cart.items.all()
        if not cart_items.exists():
            return Response({"error": "Cart is empty"}, status=400)

        order = Order.objects.create(
            user_id=user.id,
            order_number=f"ORD-{uuid.uuid4().hex[:8].upper()}",
            total_amount=cart.total_amount
        )

        for item in cart_items:
            OrderItem.objects.create(
                order=order,
                product_id=item.product_id,
                variant_id=item.variant_id,
                product_name=item.product_name,
                variant_name=item.variant_name,
                sku=item.sku,
                price=item.price,
                quantity=item.quantity
            )

        cart.is_active = False
        cart.save()

        serializer = OrderSerializer(order)
        return Response(serializer.data, status=201)

class GetOrderView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [MicroserviceJWTAuthentication]

    def get(self, request, order_id):
        try:
            order = Order.objects.get(id=order_id, user_id=request.user.id)
            serializer = OrderSerializer(order)
            return Response(serializer.data, status=200)
        except Order.DoesNotExist:
            return Response({"error": "Order not found"}, status=404)

class AdminGetOrderView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, order_id):
        try:
            order = Order.objects.get(id=order_id)
            serializer = OrderSerializer(order)
            return Response(serializer.data, status=200)
        except Order.DoesNotExist:
            return Response({"error": "Order not found"}, status=404)

# ----------------- Payment Success -----------------
class PayOrderView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [MicroserviceJWTAuthentication]

    def post(self, request, order_id):
        order = Order.objects.get(id=order_id, user_id=request.user.id)
        if order.status != "PENDING":
            return Response({"error": "Order already processed"}, status=400)

        # Create Stripe Checkout Session
        line_items = []
        for item in order.items.all():
            line_items.append({
                'price_data': {
                    'currency': 'inr', # or 'usd', default based on your locale
                    'product_data': {
                        'name': f"{item.product_name} - {item.variant_name}",
                    },
                    'unit_amount': int(item.price * 100), # Stripe expects amount in cents/paisa
                },
                'quantity': item.quantity,
            })

        domain = request.build_absolute_uri('/')[:-1] 
        success_url = request.data.get('success_url', domain + '/payment-success?session_id={CHECKOUT_SESSION_ID}')
        cancel_url = request.data.get('cancel_url', domain + '/payment-cancel')

        try:
            checkout_session = stripe.checkout.Session.create(
                line_items=line_items,
                mode='payment',
                success_url=success_url,
                cancel_url=cancel_url,
                metadata={
                    'order_id': str(order.id),
                    'user_id': str(request.user.id),
                }
            )
            Transaction.objects.create(
                order=order,
                stripe_session_id=checkout_session.id,
                amount=order.total_amount,
                status='PENDING'
            )

            return Response({
                "checkout_url": checkout_session.url
            }, status=200)
        except Exception as e:
            return Response({"error": str(e)}, status=500)

class OrderPayStatusView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [MicroserviceJWTAuthentication]

    def get(self, request, order_id):
        try:
            order = Order.objects.get(id=order_id, user_id=request.user.id)
            return Response({"order_id": order.id, "status": order.status}, status=200)
        except Order.DoesNotExist:
            return Response({"error": "Order not found"}, status=404)

import json
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

@method_decorator(csrf_exempt, name='dispatch')
class StripeWebhookView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        payload = request.body
        sig_header = request.headers.get('STRIPE_SIGNATURE')
        endpoint_secret = settings.STRIPE_WEBHOOK_SECRET

        if not sig_header:
            logger.error("Missing Stripe signature")
            return HttpResponse(status=400)

        try:
            event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
            logger.info(f"Stripe event: {event.type}")
        except Exception:
            logger.exception("Webhook verification failed")
            return HttpResponse(status=400)

        try:
            if event.type == 'checkout.session.completed':
                session = event.data.object

                metadata = getattr(session, "metadata", {}) or {}
                order_id = metadata.get('order_id')
                session_id = session.id

                if not order_id:
                    return HttpResponse(status=200)

                order_id = int(order_id)

                order = Order.objects.get(id=order_id)

                # ✅ idempotency check
                if Transaction.objects.filter(
                    order=order,
                    stripe_session_id=session_id,
                    status='SUCCESSFUL'
                ).exists():
                    return HttpResponse(status=200)

                if order.status == 'PENDING':
                    self.process_successful_payment(order, session_id)

            return HttpResponse(status=200)

        except Exception:
            logger.exception("Webhook processing failed")
            return HttpResponse(status=500)

    @transaction.atomic
    def process_successful_payment(self, order, session_id):
        # 1. Update Core statuses (Inside Atomic)
        order.status = "CONFIRMED"
        order.save(update_fields=['status'])

        try:
            transaction_record = Transaction.objects.get(order=order, stripe_session_id=session_id)
            transaction_record.status = 'SUCCESSFUL'
            transaction_record.save(update_fields=['status'])
        except Transaction.DoesNotExist:
            logger.warning(f"Transaction not found for order {order.id} and session {session_id}")

        # Ensure Delivery record exists
        Delivery.objects.get_or_create(
            order=order,
            defaults={'status': 'PENDING'}
        )

        # 2. Stock Reduction (Wrapped in its own try-except to avoid rolling back Order/Transaction)
        try:
            self._reduce_stock_logic(order)
            logger.info(f"Stock reduced successfully for order {order.id}")
        except Exception as e:
            logger.error(f"Stock reduction FAILED for order {order.id} but order remains CONFIRMED: {str(e)}")

    def _reduce_stock_logic(self, order):
        # Reduce stock via batch API (FIFO by exp_date)
        for item in order.items.all():
            qty_to_deduct = item.quantity
            logger.info(f"Attempting to deduct {qty_to_deduct} for product {item.product_name} (Variant {item.variant_id})")
            
            resp = requests.get(f"{BATCH_SERVICE_API}?variant={item.variant_id}&is_active=true")
            if resp.status_code != 200:
                raise Exception(f"Cannot fetch batches for variant {item.variant_id}. Code: {resp.status_code}")
            
            batches = resp.json()
            if not batches:
                logger.warning(f"No active batches found for variant {item.variant_id}")
                continue

            # Sort by exp_date, handle None safely
            batches.sort(key=lambda x: x.get('exp_date') or '9999-12-31')

            for batch in batches:
                if qty_to_deduct <= 0:
                    break
                
                available_qty = batch.get('qty', 0)
                batch_id = batch.get('batch_id')
                
                if not batch_id:
                    logger.warning(f"Batch found without batch_id: {batch}")
                    continue

                deduct_qty = min(qty_to_deduct, available_qty)
                if deduct_qty <= 0:
                    continue

                qty_to_deduct -= deduct_qty
                new_qty = available_qty - deduct_qty

                # Update batch
                update_resp = requests.patch(
                    f"{BATCH_SERVICE_API}{batch_id}/",
                    json={"qty": new_qty}
                )
                if update_resp.status_code != 200:
                    raise Exception(f"Failed to update batch {batch_id}. Code: {update_resp.status_code}")
                
                logger.info(f"Deducted {deduct_qty} from Batch {batch_id}. Remaining in batch: {new_qty}")


class CancelOrderView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [MicroserviceJWTAuthentication]

    @transaction.atomic
    def post(self, request, order_id):
        order = Order.objects.get(id=order_id, user_id=request.user.id)
        if order.status != "PENDING":
            return Response({"error": "Order already processed"}, status=400)

        order.status = "CANCELLED"
        order.save()

        return Response({"order_id": order.id, "status": order.status})






class get_all_ordersView(APIView):
    permission_classes=[IsAuthenticated]
    authentication_classes=[MicroserviceJWTAuthentication]

    def get(self,request):
        orders=Order.objects.filter(user_id=request.user.id)
        serializer=OrderSerializer(orders,many=True)

        return Response({"orders":serializer.data},status=status.HTTP_200_OK)

class admin_get_all_ordersView(APIView):
    permission_classes=[AllowAny]
    authentication_classes=[]

    def get(self,request):
        orders=Order.objects.all()
        serializer=OrderSerializer(orders,many=True)

        return Response({"orders":serializer.data},status=status.HTTP_200_OK)

class ActivenowView(APIView):
    permission_classes = [AllowAny]
    def get(self,request):
        return Response({"message":"Activated"},status=status.HTTP_200_OK)

class AdminUpdateOrderStatusView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    def patch(self, request, order_id):
        try:
            order = Order.objects.get(id=order_id)
            new_status = request.data.get('status')
            if new_status in ['DISPATCHED', 'IN_TRANSIT', 'DELIVERED']:
                delivery, created = Delivery.objects.get_or_create(order=order)
                delivery.status = new_status
                if new_status == 'DISPATCHED':
                    delivery.dispatched_at = timezone.now()
                    delivery.save(update_fields=['status', 'dispatched_at'])
                elif new_status == 'DELIVERED':
                    delivery.delivered_at = timezone.now()
                    delivery.save(update_fields=['status', 'delivered_at'])
                else:
                    delivery.save(update_fields=['status'])
                return Response({'message': 'Status updated'}, status=200)
            return Response({'error': 'Invalid status'}, status=400)
        except Order.DoesNotExist:
            return Response({'error': 'Order not found'}, status=404)

class VerifyPurchaseView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, user_id, product_id):
        has_purchased = OrderItem.objects.filter(
            order__user_id=user_id,
            order__delivery__status='DELIVERED',
            product_id=product_id
        ).exists()
        return Response({'has_purchased': has_purchased})
