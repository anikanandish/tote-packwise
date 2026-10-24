"""Idempotent seed data. Runs on every start but only INSERTS what is missing,
so restarting never resets inventory, prices or orders.

Product dimensions are simplified bounding boxes (retail box or the product's
outer extent) in centimetres; weights in grams. Edit them in the admin UI.
"""

from sqlalchemy.orm import Session

from .config import settings
from .models import AuditEvent, CartItem, Carton, Material, Product, Review, User
from .security import hash_password
from .services import inventory

# The standard carton sizes (nominal L x W x H in millimetres). STD-01..08 exactly as specified.
# Internal sizes start equal to the nominal sizes and are marked "not verified" until an
# admin measures a real carton. Maximum weight is NOT set (no verified figure exists).
SMALL_MAILERS = "E-commerce & retail small mailers"
SHIPPING_BOXES = "Consumer goods & electronics shipping boxes"
STANDARD_CARTONS = [
    # code, name, category, L, W, H (mm)
    ("STD-01", "Ultra-Small / Cosmetics", SMALL_MAILERS, 100, 100, 50),
    ("STD-02", "Small Mailer / Accessories", SMALL_MAILERS, 200, 150, 100),
    ("STD-03", "Medium Mailer / Skincare Kit", SMALL_MAILERS, 230, 150, 100),
    ("STD-04", "Standard E-commerce Box", SMALL_MAILERS, 300, 230, 100),
    ("STD-05", "Shoe Box / Small Gadgets", SHIPPING_BOXES, 300, 200, 130),
    ("STD-06", "Medium Apparel / Electronics", SHIPPING_BOXES, 360, 250, 150),
    ("STD-07", "Large Multi-Item Box", SHIPPING_BOXES, 460, 360, 200),
    ("STD-08", "Heavy Gadget Carrier", SHIPPING_BOXES, 290, 280, 130),
    # Eight more sizes added for the 16-carton warehouse. Common e-commerce sizes chosen to fill
    # the gaps in the first eight (mostly height: tall bottles, jars and gift sets). Nominal sizes,
    # not measured; stock and price are SAMPLE values like the first eight.
    ("STD-09", "Tall Bottle Mailer", SMALL_MAILERS, 150, 100, 150),
    ("STD-10", "Flat Book Mailer", SMALL_MAILERS, 250, 180, 50),
    ("STD-11", "Tall Cosmetics Box", SMALL_MAILERS, 200, 150, 150),
    ("STD-12", "Document / Flat Gift Box", SMALL_MAILERS, 320, 240, 60),
    ("STD-13", "Cube Gift Box", SHIPPING_BOXES, 200, 200, 200),
    ("STD-14", "Tall Vase / Diffuser Box", SHIPPING_BOXES, 120, 120, 250),
    ("STD-15", "Medium Tall Box", SHIPPING_BOXES, 300, 200, 200),
    ("STD-16", "Large Flat Box", SHIPPING_BOXES, 400, 300, 100),
]
BASELINE_CODE = "STD-07"   # largest standard carton: the comparison for savings
SAMPLE_STOCK, SAMPLE_MIN_STOCK = 40, 8

# Cartons from earlier versions. Each set is switched off once when an older database is
# upgraded, so only the standard sizes are used. History keeps its snapshots.
RETIRED_SETS = {
    "retire_legacy_cartons": ("CTN-S", "CTN-M", "CTN-L", "CTN-XL", "CTN-CUSTOM"),
    "retire_six_box_cartons": ("BOX-1", "BOX-2", "BOX-3", "BOX-4", "BOX-5", "BOX-6"),
}


def sample_board_price(L_mm: int, W_mm: int, H_mm: int) -> float:
    """SAMPLE price only: board area of a regular slotted carton blank, priced with the
    configurable BOARD_COST_PER_M2 + BOX_MAKE_COST. Not a supplier quote."""
    from .services.feasibility import custom_box_cost
    return custom_box_cost([L_mm / 10, W_mm / 10, H_mm / 10])["unit_cost"]


MATERIALS = [
    # code, name, unit, stock, min, cost ₹, notes
    ("BUBBLE", "Bubble wrap", "sheet", 500, 80, 4.0, "30 × 30 cm sheet; one sheet wraps one small fragile item"),
    ("KRAFT", "Kraft paper void fill", "sheet", 1200, 150, 1.5, "Crumpled to fill empty space"),
    ("FOAM", "Foam corner insert", "piece", 120, 20, 9.0, "For tall glassware"),
    ("POLYBAG", "Sealable poly bag", "bag", 300, 40, 2.0, "Seals liquids against leaks"),
    ("TISSUE", "Tissue paper", "sheet", 400, 50, 0.8, "Keeps bags and textiles in shape"),
]

# (slug, name, brand, category, price, L, W, H, grams, fragile, padding, orientation,
#  material, qty/unit, handling, restrictions, shape, tone, featured, stock, rating, description)
PRODUCTS = [
    ("velvet-matte-lipstick", "Velvet Matte Lipstick", "Maison Rouge", "Beauty", 1299, 2.5, 2.5, 8.5, 30, False, 0, "any",
     None, 0, "Standard item.", "", "lipstick", "#8E2A35", True, 140, 4.7,
     "A weightless matte in a deep wine shade. Long-wear, non-drying, finished in a weighted metal bullet."),
    ("gentle-nail-polish-remover", "Gentle Nail Polish Remover 150 ml", "Atelier Nail", "Beauty", 449, 6, 4, 13, 170,
     False, 0.5, "upright", "POLYBAG", 1, "Liquid. Seal in a poly bag and keep the cap facing up.",
     "Contains acetone: keep upright and away from heat.", "flatbottle", "#F2C9C4", False, 160, 4.4,
     "Acetone-based remover with glycerin and vitamin E that lifts colour without stripping the nail."),
    ("precision-liquid-eyeliner", "Precision Liquid Eyeliner", "Noir Studio", "Beauty", 699, 1.5, 1.5, 13, 12, False, 0,
     "any", None, 0, "Standard item.", "", "pen", "#1F1B1E", True, 220, 4.6,
     "Felt-tip liner with a 0.1 mm point for a crisp wing. Smudge-proof for up to 16 hours."),
    ("rose-oud-eau-de-parfum", "Rose Oud Eau de Parfum 50 ml", "Maison Rouge", "Beauty", 4850, 8, 5, 12, 310, True, 1.0,
     "upright", "BUBBLE", 1, "Glass bottle. Wrap in bubble wrap, keep upright and cushion every side.",
     "Flammable liquid: ground shipping only.", "perfume", "#C98B7A", True, 60, 4.8,
     "Turkish rose over smoked oud and saffron. Hand-finished glass flacon with a weighted cap."),
    ("hydra-silk-serum", "Hydra Silk Serum 30 ml", "Lumière", "Beauty", 2199, 4, 4, 12, 120, True, 1.0, "upright",
     "BUBBLE", 1, "Glass dropper bottle. Wrap and keep upright.", "", "dropper", "#E8D2B0", False, 80, 4.5,
     "Hyaluronic acid and niacinamide in a silky, fast-absorbing serum for daily hydration."),
    ("cloud-cream-moisturiser", "Cloud Cream Moisturiser", "Lumière", "Beauty", 1799, 7, 7, 6, 220, True, 1.0, "any",
     "BUBBLE", 1, "Glass jar. Wrap before packing.", "", "jar", "#F3E7DA", False, 75, 4.6,
     "A whipped, oil-free moisturiser with ceramides. Comes in a refillable frosted-glass jar."),
    ("satin-glow-highlighter", "Satin Glow Highlighter", "Noir Studio", "Beauty", 1199, 8, 8, 1.5, 60, True, 0.5, "any",
     "BUBBLE", 1, "Pressed powder can crack. Wrap and do not drop.", "", "compact", "#D9B88F", False, 90, 4.3,
     "A finely milled champagne highlighter that melts into skin for a soft, lit-from-within glow."),
    ("volume-lash-mascara", "Volume Lash Mascara", "Noir Studio", "Beauty", 899, 2, 2, 14, 20, False, 0, "any",
     None, 0, "Standard item.", "", "pen", "#2B2B2B", False, 180, 4.2,
     "Buildable volume without clumps. Hourglass brush and a tubing formula that washes off with warm water."),
    ("aura-wireless-headphones", "Aura Wireless Headphones", "Sonora", "Electronics", 8999, 20, 17, 9, 380, True, 1.0,
     "any", "BUBBLE", 2, "Electronics. Wrap the case in two sheets of bubble wrap.", "Contains a lithium-ion battery.",
     "headphones", "#2E2A2B", True, 35, 4.7,
     "Hybrid noise cancelling, 40-hour battery and memory-foam ear cushions wrapped in protein leather."),
    ("pebble-earbuds", "Pebble True Wireless Earbuds", "Sonora", "Electronics", 3499, 7, 6, 3.5, 90, False, 0, "any",
     None, 0, "Standard item.", "Contains a lithium-ion battery.", "earbuds", "#EDE6DD", False, 70, 4.4,
     "Pocketable earbuds with a pebble-smooth charging case, six-hour playback and clear call mics."),
    ("braided-usb-c-cable", "Braided USB-C Cable 2 m", "Volt & Co", "Electronics", 799, 12, 10, 3, 70, False, 0, "any",
     None, 0, "Standard item.", "", "cable", "#A35D4F", False, 260, 4.5,
     "100 W fast-charging USB-C to USB-C, wrapped in a tangle-free braided sleeve."),
    ("leather-phone-case", "Minimal Leather Phone Case", "Volt & Co", "Electronics", 1499, 17, 9, 2, 60, False, 0, "any",
     None, 0, "Standard item.", "", "phonecase", "#6B3A2E", False, 120, 4.3,
     "Vegetable-tanned leather that patinas with use. Raised edges and a soft microfibre lining."),
    ("orbit-smartwatch", "Orbit Smartwatch", "Tempo", "Electronics", 12999, 10, 9, 8, 210, True, 1.0, "upright",
     "BUBBLE", 1, "Boxed electronics with glass face. Wrap and keep the box upright.", "Contains a lithium-ion battery.",
     "watch", "#3A3536", True, 30, 4.6,
     "AMOLED display, heart-rate and sleep tracking, seven-day battery and a brushed steel case."),
    ("mini-bluetooth-speaker", "Mini Bluetooth Speaker", "Sonora", "Electronics", 2999, 9, 9, 10, 340, False, 0.5,
     "any", None, 0, "Standard item.", "Contains a lithium-ion battery.", "speaker", "#722F37", False, 55, 4.4,
     "Room-filling 360° sound from a speaker the size of a coffee cup. Splash resistant."),
    ("cashmere-blend-scarf", "Cashmere Blend Scarf", "Atelier", "Fashion", 3999, 25, 20, 4, 220, False, 0, "any",
     "TISSUE", 1, "Fold along existing creases and wrap in tissue.", "", "scarf", "#B98A6E", True, 45, 4.8,
     "A generous wrap in a cashmere and merino blend, brushed for a soft hand-feel."),
    ("structured-mini-tote", "Structured Mini Tote", "TOTE Studio", "Fashion", 5499, 26, 12, 20, 520, False, 0,
     "upright", "TISSUE", 2, "Stuff with tissue so the bag keeps its shape; pack standing up.", "", "bag", "#722F37",
     True, 25, 4.7, "Our signature mini tote in pebbled leather with a detachable strap and a suede interior."),
    ("tortoiseshell-sunglasses", "Tortoiseshell Sunglasses", "Riviera", "Fashion", 2799, 16, 7, 5, 110, True, 0.5,
     "any", "BUBBLE", 1, "Hard case. Wrap so lenses cannot be pressed.", "", "sunglasses", "#5A3A2A", False, 60, 4.5,
     "Hand-polished acetate frames with UV400 polarised lenses, supplied in a hard case."),
    ("silk-scrunchie-set", "Silk Scrunchie Set", "Atelier", "Fashion", 799, 12, 10, 3, 40, False, 0, "any", None, 0,
     "Standard item.", "", "scrunchie", "#D9B88F", False, 150, 4.6,
     "Three mulberry-silk scrunchies that are gentle on hair. Ivory, sand and wine."),
    ("leather-card-holder", "Leather Card Holder", "TOTE Studio", "Fashion", 1899, 11, 8, 1.5, 50, False, 0, "any",
     None, 0, "Standard item.", "", "cardholder", "#3B2A26", False, 110, 4.5,
     "Slim four-slot card holder with a central pocket, hand-painted edges and a debossed monogram."),
    ("pearl-drop-earrings", "Pearl Drop Earrings", "Riviera", "Fashion", 2499, 8, 8, 4, 40, False, 0, "any", None, 0,
     "Boxed jewellery.", "", "earrings", "#EFE6D8", False, 50, 4.7,
     "Freshwater pearls on gold-plated sterling silver hooks. Presented in a linen box."),
    ("amber-soy-candle", "Amber Soy Candle", "Hearth", "Home & Living", 1599, 9, 9, 10, 450, True, 1.0, "upright",
     "BUBBLE", 1, "Glass vessel. Wrap and keep upright.", "Keep upright; wax can shift in heat.", "candle", "#B8743A",
     True, 70, 4.6, "Hand-poured soy wax with amber, tonka and vanilla. Around 45 hours of burn time."),
    ("stoneware-coffee-mug", "Stoneware Coffee Mug", "Hearth", "Home & Living", 899, 12, 9, 10, 380, True, 1.0,
     "upright", "BUBBLE", 1, "Ceramic. Wrap including the handle.", "", "mug", "#E9DFD1", False, 90, 4.4,
     "Reactive-glaze stoneware, thrown and glazed by hand. Holds 350 ml."),
    ("linen-napkin-set", "Linen Napkin Set of 4", "Hearth", "Home & Living", 1299, 22, 16, 4, 300, False, 0, "any",
     None, 0, "Standard item.", "", "linen", "#CDBBA3", False, 80, 4.5,
     "Stone-washed European linen napkins that soften with every wash."),
    ("ceramic-bud-vase", "Ceramic Bud Vase", "Hearth", "Home & Living", 1899, 8, 8, 16, 420, True, 1.5, "upright",
     "FOAM", 1, "Tall ceramic. Use a foam insert and keep upright.", "", "vase", "#F1E9DE", False, 40, 4.6,
     "A slender matte-glazed vase for a single stem. Each piece varies slightly."),
    ("cedar-reed-diffuser", "Cedar Reed Diffuser 200 ml", "Hearth", "Home & Living", 2199, 8, 8, 22, 520, True, 1.0,
     "upright", "BUBBLE", 2, "Tall glass bottle with liquid. Reeds packed separately inside the box.",
     "Keep upright; contains fragrance oil.", "diffuser", "#8C6A4F", False, 30, 4.3,
     "Cedarwood, vetiver and bergamot in a tall amber-glass bottle with rattan reeds."),
    ("the-quiet-edit", "The Quiet Edit (Hardcover)", "Folio Press", "Books & Stationery", 899, 23, 15, 3, 520, False, 0,
     "any", None, 0, "Standard item. Protect corners.", "", "book", "#722F37", False, 100, 4.7,
     "Essays on slow style and keeping fewer, better things. Cloth-bound with a ribbon marker."),
    ("dot-grid-notebook", "Dot Grid Notebook A5", "Papier", "Books & Stationery", 699, 21, 15, 1.5, 280, False, 0, "any",
     None, 0, "Standard item.", "", "notebook", "#D9B88F", True, 200, 4.8,
     "Lay-flat binding, 160 pages of 100 gsm ivory paper that takes fountain-pen ink without bleed."),
    ("brass-fountain-pen", "Brass Fountain Pen", "Papier", "Books & Stationery", 2499, 16, 5, 3, 80, False, 0.5, "any",
     None, 0, "Boxed pen.", "", "fountainpen", "#B08D57", False, 45, 4.6,
     "Solid brass body that develops a warm patina, fitted with a fine steel nib and converter."),
    ("pressed-flower-bookmarks", "Pressed Flower Bookmarks", "Papier", "Books & Stationery", 399, 15, 6, 0.5, 20, False, 0,
     "any", None, 0, "Standard item.", "", "bookmark", "#C98B7A", False, 180, 4.5,
     "A set of three bookmarks with real pressed flowers sealed under matte laminate."),
    ("desk-planner-2027", "Desk Planner 2027", "Papier", "Books & Stationery", 1199, 25, 18, 2, 420, False, 0, "any",
     None, 0, "Standard item.", "", "planner", "#3B3536", False, 120, 4.4,
     "Week-on-two-pages planner with monthly spreads, linen cover and two ribbon markers."),
]

REVIEW_TEMPLATES = [
    ("Ananya R.", 5, "Exactly as pictured", "Beautifully made and arrived well packed. Would buy again."),
    ("Karthik S.", 4, "Very good", "Great quality for the price. Took a day longer than expected to arrive."),
    ("Meera P.", 5, "A favourite", "I use it every day. The finish feels genuinely premium."),
    ("Rahul V.", 4, "Nice gift", "Bought it as a gift and it went down well. Packaging was neat, not wasteful."),
]

DEMO_ORDER = [("velvet-matte-lipstick", 1), ("gentle-nail-polish-remover", 1), ("precision-liquid-eyeliner", 2),
              ("rose-oud-eau-de-parfum", 1)]


def seed(db: Session) -> dict:
    info = {}
    actor = "system:seed"
    # cartons & materials
    inserted = set()
    for code, name, category, L, W, H in STANDARD_CARTONS:
        if db.query(Carton).filter(Carton.code == code).first():
            continue   # never overwrite admin edits or stock
        inserted.add(code)
        sample = settings.seed_sample_carton_values
        c = Carton(code=code, name=name, category=category,
                   nominal_length_mm=L, nominal_width_mm=W, nominal_height_mm=H,
                   length_mm=L, width_mm=W, height_mm=H, internal_verified=False,
                   max_weight_g=None, unit_cost=sample_board_price(L, W, H) if sample else None,
                   stock=SAMPLE_STOCK if sample else 0, min_stock=SAMPLE_MIN_STOCK if sample else 0,
                   is_predefined=True, is_baseline=False,
                   sample_fields=["unit_cost", "stock", "min_stock"] if sample else [],
                   notes="Standard size. Internal dimensions not yet measured; nominal size is used for fitting.")
        db.add(c)
        db.flush()
        inventory.initial(db, "carton", c, actor, "Seed stock (SAMPLE quantity)" if sample else "Seed (no stock)")
    # Made-to-measure boxes (edge cases only, see CUSTOM_BOX_WHEN_STOCK_OVER). One catalogue row stands
    # for the board blanks; each plan carries its own size and an estimated board price.
    if not db.query(Carton).filter(Carton.code == settings.made_to_measure_code).first():
        sample = settings.seed_sample_carton_values
        c = Carton(code=settings.made_to_measure_code, name="Made-to-measure box", category="Cut to size per order",
                   nominal_length_mm=1, nominal_width_mm=1, nominal_height_mm=1,
                   length_mm=1, width_mm=1, height_mm=1, internal_verified=False, max_weight_g=None,
                   unit_cost=None, stock=200 if sample else 0, min_stock=20 if sample else 0,
                   is_predefined=False, is_baseline=False,
                   sample_fields=["stock", "min_stock"] if sample else [],
                   notes="Board blanks for boxes cut to the packing algorithm's own design. The size is set per "
                         "order (shown on the plan) and priced with the board-area estimate. Used only when no "
                         "stock carton fits or the best one is much larger than needed.")
        db.add(c)
        db.flush()
        inventory.initial(db, "carton", c, actor, "Seed stock (SAMPLE quantity)" if sample else "Seed (no stock)")
    for action, codes in RETIRED_SETS.items():
        if db.query(AuditEvent).filter(AuditEvent.action == action).first():
            continue
        retired = []
        for c in db.query(Carton).filter(Carton.code.in_(codes)).all():
            if c.is_active or c.is_baseline:
                c.is_active, c.is_baseline = False, False
                retired.append(c.code)
        db.add(AuditEvent(entity="carton", entity_id=None, action=action, actor=actor,
                          details={"retired": retired, "now_using": [row[0] for row in STANDARD_CARTONS]}))
    # Baseline: set once, when the standard set is first added (an admin may change it later).
    db.flush()
    if BASELINE_CODE in inserted and not db.query(Carton).filter(Carton.is_baseline.is_(True)).first():
        db.query(Carton).filter(Carton.code == BASELINE_CODE).update({Carton.is_baseline: True})
    for code, name, unit, stock, mn, cost, notes in MATERIALS:
        if not db.query(Material).filter(Material.code == code).first():
            m = Material(code=code, name=name, unit=unit, stock=stock, min_stock=mn, unit_cost=cost, notes=notes)
            db.add(m)
            inventory.initial(db, "material", m, actor, "Seed stock")

    # products & demo reviews
    for i, row in enumerate(PRODUCTS):
        (slug, name, brand, cat, price, L, W, H, g, fragile, pad, orient, mat, qty, handling, restr, shape, tone,
         featured, stock, rating, desc) = row
        if db.query(Product).filter(Product.slug == slug).first():
            continue
        p = Product(slug=slug, name=name, brand=brand, category=cat, price=price, length_cm=L, width_cm=W, height_cm=H,
                    weight_g=g, fragile=fragile, padding_cm=pad, orientation=orient, protection_material_code=mat,
                    protection_qty_per_unit=qty, handling_instructions=handling, restrictions=restr,
                    art={"shape": shape, "tone": tone}, featured=featured, stock=stock, rating=rating,
                    rating_count=24 + (i * 37) % 180, description=desc)
        db.add(p)
        db.flush()
        for j in range(3):
            a, r, t, b = REVIEW_TEMPLATES[(i + j) % len(REVIEW_TEMPLATES)]
            db.add(Review(product_id=p.id, author=a, rating=r, title=t, body=b, is_demo=True))

    db.commit()

    # demo customer + ready-made demo order (only on the very first run)
    demo_email, demo_pwd = "demo@tote.local", __import__("os").getenv("DEMO_CUSTOMER_PASSWORD", "")
    if demo_pwd and not db.query(User).filter(User.email == demo_email).first():
        db.add(User(email=demo_email, name="Demo Customer", password_hash=hash_password(demo_pwd), role="customer"))
        db.commit()
    demo_user = db.query(User).filter(User.email == demo_email).first()
    already = db.query(AuditEvent).filter(AuditEvent.action == "seed_demo_order").first()
    if settings.seed_demo_order and demo_user and not already:
        from .services.orders import checkout
        for slug, q in DEMO_ORDER:
            prod = db.query(Product).filter(Product.slug == slug).first()
            db.add(CartItem(user_id=demo_user.id, product_id=prod.id, quantity=q))
        db.commit()
        order = checkout(db, demo_user, {"name": "Demo Customer", "email": demo_email, "phone": "9000000000"},
                         {"line1": "12 Demo Street", "line2": "", "city": "Chennai", "state": "Tamil Nadu",
                          "postal_code": "600001", "country": "India"}, {"method": "card"})
        db.add(AuditEvent(entity="order", entity_id=order.id, order_id=order.id, action="seed_demo_order",
                          actor=actor, details={"code": order.code}))
        db.commit()
        info["demo_order"] = order.code
    return info
