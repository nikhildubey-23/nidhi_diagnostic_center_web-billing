"""Seed data: roles, permissions, settings, categories, sample services.

Run via `flask seed`. Admin users are created separately with
`flask create-admin` so no passwords live in source code.
"""
from decimal import Decimal

from app.extensions import db
from app.models.content import FAQ, WebsiteContent
from app.models.service import Service, ServiceCategory
from app.models.user import Permission, Role, ROLE_LABELS, ROLE_PERMISSIONS
from app.utils.helpers import SETTING_DEFAULTS, Setting

PERMISSION_DESCRIPTIONS = {
    "dashboard.view": "View the admin dashboard",
    "bookings.manage": "Manage bookings/appointments",
    "patients.manage": "Manage patients",
    "services.manage": "Manage diagnostic services & prices",
    "billing.manage": "Create/manage invoices",
    "payments.manage": "Record payments",
    "reports.manage": "Upload & manage diagnostic reports",
    "finreports.view": "View financial reports & collections",
    "users.manage": "Manage staff users",
    "settings.manage": "Manage business/website settings",
    "audit.view": "View audit logs",
}

CATEGORIES = [
    ("Sonography / Ultrasound", "sonography", {"icon": "\U0001f4a0"}),
    ("X-Ray", "x-ray", {"icon": "\u2620"}),
    ("CT Scan", "ct-scan", {"icon": "\u2699"}),
    ("Pathology", "pathology", {"icon": "\U0001f9ea"}),
    ("Health Checkups", "health-checkups", {"icon": "\u2764"}),
]

SERVICES = [
    # code, name, category_slug, price, tax, prep, duration, description
    ("USG-ABD", "USG Whole Abdomen", "sonography", 800, 0,
     "Fast for 6\u20138 hours before the scan. Drink water as advised for a full bladder.",
     20, "Ultrasound of abdomen to examine liver, gallbladder, kidneys, pancreas and spleen."),
    ("USG-PEL", "USG Pelvis", "sonography", 700, 0,
     "Drink 1 litre of water 1 hour before; do not urinate until scan completes.",
     15, "Pelvic ultrasound for urinary bladder, uterus (female) and prostate region (male)."),
    ("USG-OBST", "Obstetric USG (Pregnancy)", "sonography", 900, 0,
     "Carry previous pregnancy records if any.",
     25, "Antenatal ultrasound for fetal growth, position and wellbeing."),
    ("USG-KUB", "USG KUB", "sonography", 600, 0,
     "Fast for 4\u20136 hours; full bladder required.",
     15, "Kidney, ureter and bladder ultrasound \u2014 commonly used for stones and urinary issues."),
    ("XRAY-CHEST", "X-Ray Chest PA View", "x-ray", 300, 0,
     "Remove metal items & wear comfortable clothing. Inform staff if pregnant.",
     10, "Digital chest X-ray for lungs, heart silhouette and ribcage."),
    ("XRAY-KNEE", "X-Ray Knee Joint", "x-ray", 350, 0,
     "No preparation needed.",
     10, "Knee joint X-ray for fractures, arthritis and joint spaces."),
    ("XRAY-SPINE", "X-Ray Lumbosacral Spine", "x-ray", 450, 0,
     "No special preparation.",
     12, "LS spine X-ray for backache evaluation."),
    ("CT-BRAIN", "CT Scan Brain (Plain)", "ct-scan", 2500, 0,
     "Fast 4 hours if contrast is planned. Remove jewellery/metal items.",
     20, "Computed tomography of brain for stroke, trauma, headache workup."),
    ("CT-ABD", "CT Abdomen (Contrast)", "ct-scan", 4500, 0,
     "Fast 6 hours. Contrast will be administered; kidney function test advisable.",
     30, "Contrast CT of abdomen & pelvis."),
    ("CT-CHEST", "CT Chest (HRCT)", "ct-scan", 3500, 0,
     "Hold breath instructions given at centre. Inform staff if pregnant.",
     20, "High-resolution chest CT for lung pathology."),
    ("PATH-CBC", "Complete Blood Count (CBC)", "pathology", 350, 0,
     "No fasting required.",
     5, "Blood count screening: hemoglobin, WBC, platelets."),
    ("PATH-LFT", "Liver Function Test (LFT)", "pathology", 600, 0,
     "8\u201310 hours fasting preferred.",
     5, "Panel of tests assessing liver health."),
    ("PATH-KFT", "Kidney Function Test (KFT)", "pathology", 650, 0,
     "8 hours fasting preferred; stay hydrated.",
     5, "Creatinine, urea, uric acid and electrolytes."),
    ("PATH-SUGAR", "Blood Sugar (Fasting & PP)", "pathology", 150, 0,
     "Fasting sample + post-prandial after 2 hrs of meal.",
     5, "Diabetes screening and monitoring."),
    ("PATH-LIPID", "Lipid Profile", "pathology", 550, 0,
     "12\u201314 hours fasting required.",
     5, "Cholesterol, triglycerides, HDL/LDL profile."),
    ("PKG-FULL", "Full Body Health Checkup", "health-checkups", 1999, 0,
     "12 hours fasting; carry morning urine sample.",
     120, "Comprehensive panel: CBC, sugar, lipid, liver, kidney, thyroid, urine."),
    ("PKG-DIABETIC", "Diabetic Checkup Package", "health-checkups", 999, 0,
     "Follow medicine schedule as usual; bring reports of last 3 months if any.",
     60, "Sugar profiles, HbA1c, kidney & eye screening basics."),
]


def _ensure_permissions():
    perms = {}
    created = 0
    for code in ROLE_PERMISSIONS["super_admin"]:
        p = Permission.query.filter_by(code=code).first()
        if p is None:
            p = Permission(code=code,
                           description=PERMISSION_DESCRIPTIONS.get(code, ""))
            db.session.add(p)
            created += 1
        perms[code] = p
    return perms, created


def run_seed() -> str:
    notes = []

    perms, perm_count = _ensure_permissions()
    notes.append(f"{perm_count} permissions")

    role_count = 0
    for name, label in ROLE_LABELS.items():
        role = Role.query.filter_by(name=name).first()
        if role is None:
            role = Role(name=name, label=label)
            db.session.add(role)
            role_count += 1
        role.permissions = [perms[c] for c in ROLE_PERMISSIONS[name]]
    notes.append(f"{role_count} roles")

    setting_rows = 0
    existing_keys = {k for (k,) in db.session.query(Setting.key)}
    for key, value in SETTING_DEFAULTS.items():
        if key not in existing_keys:
            db.session.add(Setting(key=key, value=value))
            setting_rows += 1
    notes.append(f"{setting_rows} settings")

    cat_map = {}
    new_cats = 0
    for name, slug, extra in CATEGORIES:
        cat = ServiceCategory.query.filter_by(slug=slug).first()
        if cat is None:
            cat = ServiceCategory(name=name, slug=slug,
                                  icon=extra.get("icon"),
                                  sort_order=len(cat_map))
            db.session.add(cat)
            new_cats += 1
        cat_map[slug] = cat
    db.session.flush()
    notes.append(f"{new_cats} categories")

    svc_count = 0
    for code, name, slug, price, tax, prep, dur, desc in SERVICES:
        if Service.query.filter_by(code=code).first() is None:
            db.session.add(Service(
                code=code, name=name, category_id=cat_map[slug].id,
                price=Decimal(price), tax_percent=Decimal(tax),
                preparation_instructions=prep, duration_minutes=dur,
                description=desc,
            ))
            svc_count += 1
    notes.append(f"{svc_count} services")

    content_defaults = {
        "home_hero_title": ("home_hero_title", "Advanced Diagnostics You Can Trust",
                            "Accurate sonography, X-Ray, CT scan and lab tests in "
                            "Sarkanda, Bilaspur \u2014 with same-day appointments and "
                            "digital reports."),
        "about_intro": ("about_intro", "About Nidhi Diagnostic",
                        "Nidhi Diagnostic is a modern diagnostic centre serving "
                        "Bilaspur, Chhattisgarh with advanced imaging and pathology "
                        "services under one roof."),
        "about_mission": ("about_mission", "Our Mission",
                          "To make accurate, affordable diagnostics accessible to every "
                          "family in Bilaspur \u2014 combining qualified professionals, "
                          "modern equipment and compassionate care."),
        "why_choose_us": ("why_choose_us", "Why Choose Us",
                          "Experienced radiologists and certified lab technicians|"
                          "Digital X-Ray, Colour Doppler & multi-slice CT under one roof|"
                          "Same-day reports for most tests|"
                          "Transparent pricing with no hidden charges|"
                          "Home sample collection available on request"),
    }
    new_content = 0
    for key, (key_, title, body) in content_defaults.items():
        if WebsiteContent.query.filter_by(key=key_).first() is None:
            db.session.add(WebsiteContent(key=key_, title=title, body=body))
            new_content += 1
    notes.append(f"{new_content} content blocks")

    if FAQ.query.count() == 0:
        faqs = [
            ("Do I need an appointment?",
             "Walk-ins are welcome, but booking online or by phone guarantees your slot and reduces waiting time."),
            ("How long do reports take?",
             "Most blood test reports are ready within 4\u20136 hours. X-Ray and ultrasound reports are usually ready the same day. CT scans may take up to 24 hours."),
            ("What should I bring for my test?",
             "Please carry a doctor's prescription/referral (if any), previous reports, photo ID and this booking reference number."),
            ("Which payment methods are accepted?",
             "We accept Cash, UPI, Debit/Credit cards and bank transfer. You receive a printed GST invoice for every payment."),
            ("Is home sample collection available?",
             "Yes, for most pathology tests within Bilaspur city limits. Call us to schedule a home visit."),
        ]
        for i, (q, a) in enumerate(faqs):
            db.session.add(FAQ(question=q, answer=a, sort_order=i))
        notes.append("5 FAQs")

    return ", ".join(notes)


def seed_demo_data():
    """Dev-only demo patients/bookings/invoices."""
    from datetime import datetime, timedelta

    from app.models.billing import Invoice, InvoiceItem, Payment
    from app.models.booking import Booking
    from app.models.patient import Patient
    from app.utils.numbering import next_booking_code, next_invoice_code, next_patient_code

    out = []
    demo_patients = [
        ("Rahul Sharma", "9876543210", "male", 32),
        ("Priya Verma", "9876543211", "female", 28),
        ("Mohan Patel", "9876543212", "male", 45),
    ]
    patients = {}
    for name, mobile, gender, age in demo_patients:
        p = Patient.query.filter_by(mobile=mobile).first()
        if not p:
            p = Patient(patient_code=next_patient_code(), full_name=name,
                        mobile=mobile, gender=gender, age=age)
            db.session.add(p)
            db.session.flush()
            out.append(f"patient {p.full_name}")
        patients[mobile] = p

    today = date.today()
    services = {s.code: s for s in Service.query.all()}
    combos = [
        ("9876543210", ["USG-ABD"], "confirmed"),
        ("9876543211", ["XRAY-CHEST", "PATH-CBC"], "pending"),
        ("9876543212", ["CT-BRAIN", "XRAY-CHEST"], "pending"),
    ]
    for mobile, codes, status in combos:
        svc = services[codes[0]]
        b = Booking(
            booking_code=next_booking_code(),
            patient_id=patients[mobile].id,
            patient_name=patients[mobile].full_name,
            mobile=mobile,
            service_id=svc.id,
            preferred_date=today + timedelta(days=1),
            status=status,
        )
        db.session.add(b)
        db.session.flush()
        out.append(f"booking {b.booking_code}")

    # One finalized invoice for Rahul: USG + XRay
    rahul = patients["9876543210"]
    inv = Invoice(invoice_code=next_invoice_code(), patient_id=rahul.id)
    for c, qty in (("USG-ABD", 1), ("XRAY-CHEST", 1)):
        s = services[c]
        inv.items.append(InvoiceItem(service_id=s.id, service_name_snapshot=s.name,
                                     qty=qty, rate=s.price,
                                     discount_amount=Decimal(50) if c == "USG-ABD" else Decimal(0),
                                     tax_percent=s.tax_percent))
    inv.created_by_id = None
    db.session.add(inv)
    db.session.flush()
    inv.finalize(user_id=None)
    inv.add_payment(Decimal(inv.grand_total), "cash")
    inv.recalculate()
    out.append(f"invoice {inv.invoice_code}")
    return out
