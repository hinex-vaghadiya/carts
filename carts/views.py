from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db import transaction
import uuid
import requests
from rest_framework import serializers
from .models import Cart, CartItem, Order, OrderItem
from .serializers import CartSerializer, CartItemSerializer, OrderSerializer
from .authentication import MicroserviceJWTAuthentication

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



# ----------------- Payment Success -----------------
class PayOrderView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [MicroserviceJWTAuthentication]

    @transaction.atomic
    def post(self, request, order_id):
        order = Order.objects.get(id=order_id, user_id=request.user.id)
        if order.status != "PENDING":
            return Response({"error": "Order already processed"}, status=400)

        order.status = "PAID"
        order.save()

        # Reduce stock via batch API (FIFO by exp_date)
        for item in order.items.all():
            qty_to_deduct = item.quantity
            resp = requests.get(f"{BATCH_SERVICE_API}?variant={item.variant_id}&is_active=true")
            if resp.status_code != 200:
                raise Exception(f"Cannot fetch batches for variant {item.variant_id}")
            batches = resp.json()
            batches.sort(key=lambda x: x['exp_date'])

            for batch in batches:
                if qty_to_deduct <= 0:
                    break
                available_qty = batch['qty']
                deduct_qty = min(qty_to_deduct, available_qty)
                qty_to_deduct -= deduct_qty

                # Update batch
                update_resp = requests.patch(
                    f"{BATCH_SERVICE_API}{batch['batch_id']}/",
                    json={"qty": available_qty - deduct_qty}
                )
                if update_resp.status_code != 200:
                    raise Exception(f"Failed to update batch {batch['batch_id']}")

        return Response({"order_id": order.id, "status": order.status})


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



class ActivenowView(APIView):
    def get(self,request):
        return Response({"message":"Activated"},status=status.HTTP_200_OK)