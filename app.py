import streamlit as st
import sqlite3
import hashlib
import secrets
import hmac
import os
import random
import time
import smtplib
import base64
from email.message import EmailMessage

try:
    from google import genai
except ImportError:
    genai = None

st.set_page_config(
    page_title="PharmaPath",
    page_icon="💊",
    layout="wide"
)

DB = "pharmapath.db"


# ==================== DATABASE ====================

def connect():
    return sqlite3.connect(DB, check_same_thread=False)


def get_columns(cursor, table):
    return [
        row[1]
        for row in cursor.execute(
            f"PRAGMA table_info({table})"
        ).fetchall()
    ]


def setup():
    con = connect()
    cur = con.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        name TEXT,
        email TEXT UNIQUE,
        password_hash TEXT,
        password TEXT,
        role TEXT DEFAULT 'consumer',
        user_type TEXT,
        shop_name TEXT DEFAULT '',
        area TEXT DEFAULT ''
    )
    """)

    columns = get_columns(cur, "users")

    user_fields = {
        "username": "TEXT",
        "name": "TEXT DEFAULT ''",
        "email": "TEXT",
        "password_hash": "TEXT",
        "password": "TEXT",
        "role": "TEXT DEFAULT 'consumer'",
        "user_type": "TEXT",
        "shop_name": "TEXT DEFAULT ''",
        "area": "TEXT DEFAULT ''"
    }

    for column, definition in user_fields.items():
        if column not in columns:
            cur.execute(
                f"ALTER TABLE users ADD COLUMN {column} {definition}"
            )

    columns = get_columns(cur, "users")

    if "username" in columns:
        cur.execute("""
        UPDATE users
        SET name=username
        WHERE (name IS NULL OR name='')
        AND username IS NOT NULL
        """)

    if "full_name" in columns:
        cur.execute("""
        UPDATE users
        SET name=full_name
        WHERE (name IS NULL OR name='')
        AND full_name IS NOT NULL
        """)

    if "user_type" in columns:
        cur.execute("""
        UPDATE users
        SET role=user_type
        WHERE (role IS NULL OR role='')
        AND user_type IS NOT NULL
        """)

    cur.execute("""
    UPDATE users
    SET password=password_hash
    WHERE (password IS NULL OR password='')
    AND password_hash IS NOT NULL
    """)

    cur.execute("""
    UPDATE users
    SET password_hash=password
    WHERE (password_hash IS NULL OR password_hash='')
    AND password IS NOT NULL
    """)

    cur.execute("""
    UPDATE users
    SET role='consumer'
    WHERE lower(role) IN ('customer','user','buyer')
    """)

    cur.execute("""
    UPDATE users
    SET role='shopkeeper'
    WHERE lower(role) IN ('shop','seller','pharmacy')
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS medicines(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER DEFAULT 0,
        shopkeeper_id INTEGER DEFAULT 0,
        name TEXT DEFAULT '',
        medicine_name TEXT,
        quantity INTEGER DEFAULT 0,
        stock INTEGER DEFAULT 0,
        price REAL DEFAULT 0,
        photo BLOB,
        image BLOB
    )
    """)

    medicine_fields = {
        "user_id": "INTEGER DEFAULT 0",
        "shopkeeper_id": "INTEGER DEFAULT 0",
        "name": "TEXT DEFAULT ''",
        "medicine_name": "TEXT",
        "quantity": "INTEGER DEFAULT 0",
        "stock": "INTEGER DEFAULT 0",
        "price": "REAL DEFAULT 0",
        "photo": "BLOB",
        "image": "BLOB"
    }

    med_columns = get_columns(cur, "medicines")

    for column, definition in medicine_fields.items():
        if column not in med_columns:
            cur.execute(
                f"ALTER TABLE medicines ADD COLUMN {column} {definition}"
            )

    med_columns = get_columns(cur, "medicines")

    if "medicine_name" in med_columns:
        cur.execute("""
        UPDATE medicines
        SET name=medicine_name
        WHERE (name IS NULL OR name='')
        AND medicine_name IS NOT NULL
        """)

    cur.execute("""
    UPDATE medicines
    SET user_id=shopkeeper_id
    WHERE (user_id IS NULL OR user_id=0)
    AND shopkeeper_id IS NOT NULL
    """)

    cur.execute("""
    UPDATE medicines
    SET quantity=stock
    WHERE (quantity IS NULL OR quantity=0)
    AND stock IS NOT NULL
    """)

    cur.execute("""
    UPDATE medicines
    SET photo=image
    WHERE photo IS NULL AND image IS NOT NULL
    """)

    con.commit()
    con.close()


setup()


# ==================== MEDICINE PHOTOS ====================

def get_image_data(photo):
    if photo is None:
        return None

    try:
        if isinstance(photo, memoryview):
            photo = photo.tobytes()

        if isinstance(photo, (bytes, bytearray)):
            return bytes(photo) if photo else None

        if isinstance(photo, str):
            value = photo.strip()

            if not value:
                return None

            if os.path.isfile(value):
                with open(value, "rb") as file:
                    return file.read()

            if value.startswith("data:") and "," in value:
                return base64.b64decode(
                    value.split(",", 1)[1]
                )

    except Exception:
        return None

    return None


def display_medicine_photo(photo, width=180):
    image_data = get_image_data(photo)

    if image_data:
        try:
            st.image(image_data, width=width)
            return
        except Exception:
            pass

    st.markdown(
        """
        <div class="medicine-photo-placeholder">
            📷<br>
            <span>Photo not available</span>
        </div>
        """,
        unsafe_allow_html=True
    )


# ==================== PASSWORD FUNCTIONS ====================

def hash_password(password):
    salt = secrets.token_bytes(16)

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode(),
        salt,
        200000
    )

    return salt.hex() + ":" + digest.hex()


def verify_password(password, stored):
    if not stored:
        return False, False

    try:
        if ":" in stored:
            salt, digest = stored.split(":", 1)
            salt_bytes = bytes.fromhex(salt)

            for rounds in (200000, 100000):
                check = hashlib.pbkdf2_hmac(
                    "sha256",
                    password.encode(),
                    salt_bytes,
                    rounds
                ).hex()

                if hmac.compare_digest(check, digest):
                    return True, rounds != 200000

        if "$" in stored:
            salt, digest = stored.split("$", 1)

            for rounds in (100000, 200000):
                check = hashlib.pbkdf2_hmac(
                    "sha256",
                    password.encode(),
                    salt.encode(),
                    rounds
                ).hex()

                if hmac.compare_digest(check, digest):
                    return True, True

        if len(stored) == 64:
            check = hashlib.sha256(
                password.encode()
            ).hexdigest()

            if hmac.compare_digest(check, stored):
                return True, True

    except Exception:
        return False, False

    return False, False


# ==================== USER FUNCTIONS ====================

def get_user(email):
    con = connect()

    user = con.execute("""
    SELECT
        id,
        COALESCE(NULLIF(name,''),username,''),
        email,
        COALESCE(NULLIF(password,''),password_hash,''),
        COALESCE(NULLIF(role,''),user_type,'consumer'),
        shop_name,
        area
    FROM users
    WHERE lower(email)=lower(?)
    """, (email.strip(),)).fetchone()

    con.close()
    return user


def register(name, email, password, role, shop, area):
    con = connect()
    cur = con.cursor()

    columns = get_columns(cur, "users")
    password_hash = hash_password(password)

    values = {
        "name": name.strip(),
        "username": name.strip(),
        "email": email.strip().lower(),
        "password": password_hash,
        "password_hash": password_hash,
        "role": role,
        "user_type": role,
        "shop_name": shop.strip(),
        "area": area.strip()
    }

    insert_columns = [
        column
        for column in values
        if column in columns
    ]

    placeholders = ",".join(
        ["?"] * len(insert_columns)
    )

    column_names = ",".join(insert_columns)

    try:
        cur.execute(
            f"""
            INSERT INTO users ({column_names})
            VALUES ({placeholders})
            """,
            tuple(values[column] for column in insert_columns)
        )

        con.commit()
        return True, ""

    except sqlite3.IntegrityError:
        return False, "This email is already registered."

    except Exception as e:
        return False, str(e)

    finally:
        con.close()


# ==================== MEDICINE DATABASE FUNCTIONS ====================

def get_medicines(user_id):
    con = connect()

    rows = con.execute("""
    SELECT
        id,
        name,
        quantity,
        price,
        COALESCE(NULLIF(photo,X''),image)
    FROM medicines
    WHERE user_id=?
    ORDER BY name
    """, (user_id,)).fetchall()

    con.close()
    return rows


def add_medicine(user_id, name, quantity, price, photo):
    con = connect()
    cur = con.cursor()

    columns = get_columns(cur, "medicines")

    values = {
        "user_id": user_id,
        "shopkeeper_id": user_id,
        "name": name.strip(),
        "medicine_name": name.strip(),
        "quantity": quantity,
        "stock": quantity,
        "price": price,
        "photo": photo,
        "image": photo
    }

    insert_columns = [
        column
        for column in values
        if column in columns
    ]

    placeholders = ",".join(
        ["?"] * len(insert_columns)
    )

    column_names = ",".join(insert_columns)

    cur.execute(
        f"""
        INSERT INTO medicines ({column_names})
        VALUES ({placeholders})
        """,
        tuple(values[column] for column in insert_columns)
    )

    con.commit()
    con.close()


def update_medicine(mid, user_id, name, quantity, price, photo):
    con = connect()
    cur = con.cursor()

    columns = get_columns(cur, "medicines")

    values = {
        "name": name.strip(),
        "medicine_name": name.strip(),
        "quantity": quantity,
        "stock": quantity,
        "price": price,
        "photo": photo,
        "image": photo
    }

    assignments = []
    params = []

    for column, value in values.items():
        if column in columns:
            assignments.append(f"{column}=?")
            params.append(value)

    params.extend([mid, user_id])

    cur.execute(
        f"""
        UPDATE medicines
        SET {','.join(assignments)}
        WHERE id=? AND user_id=?
        """,
        tuple(params)
    )

    con.commit()
    con.close()


def delete_medicine(mid, user_id):
    con = connect()

    con.execute(
        """
        DELETE FROM medicines
        WHERE id=? AND user_id=?
        """,
        (mid, user_id)
    )

    con.commit()
    con.close()


# ==================== GEMINI CHATBOT ====================

def get_gemini_api_key():
    key = ""

    try:
        key = st.secrets.get("GEMINI_API_KEY", "")
    except Exception:
        pass

    if not key:
        key = os.getenv("GEMINI_API_KEY", "")

    return str(key).strip().strip('"').strip("'")


def chatbot(question, history):
    api_key = get_gemini_api_key()

    if not api_key:
        return (
            "Gemini API key set nahi hai. .streamlit/secrets.toml mein "
            'GEMINI_API_KEY = "YOUR_API_KEY" set karo.'
        )

    if genai is None:
        return "Google AI package install nahi hai. Terminal mein: py -m pip install -U google-genai"

    if not question or not str(question).strip():
        return "Apna question type karo."

    instructions = """
You are PharmaPath, a medicine information assistant.
Reply in simple Hindi or Hinglish matching the user's language.
Answer general questions directly and clearly. Explain what a medicine is,
its common uses, common side effects and general precautions when relevant.
Never diagnose, prescribe, recommend starting/stopping a medicine, or give
individualized doses. Never invent medical facts. Brand formulations can vary.
For overdose, breathing difficulty, severe allergic reaction, fainting,
chest pain or other emergency symptoms, advise immediate medical care.
Keep answers practical and concise.
"""

    conversation = []
    for msg in (history or [])[:-1][-10:]:
        role = "User" if msg.get("role") == "user" else "Assistant"
        content = str(msg.get("content", ""))[:2000]
        if content.strip():
            conversation.append(f"{role}: {content}")

    prompt = instructions + "\n\n"
    if conversation:
        prompt += "Previous conversation:\n" + "\n".join(conversation) + "\n\n"
    prompt += "User: " + str(question).strip()[:4000]

    try:
        client = genai.Client(api_key=api_key)

        # Hard-coded model ID par depend nahi karte. API se wahi models lo
        # jo is key/project ke liye generateContent support karte hain.
        candidates = []
        try:
            for model_info in client.models.list():
                model_name = str(getattr(model_info, "name", "") or "")
                model_name = model_name.replace("models/", "").strip()
                actions = getattr(model_info, "supported_actions", None) or []
                actions_text = " ".join(str(x).lower() for x in actions)
                if not model_name:
                    continue
                if actions_text and "generatecontent" not in actions_text.replace("_", ""):
                    continue
                if "gemini" not in model_name.lower():
                    continue
                candidates.append(model_name)
        except Exception:
            candidates = []

        # Flash models ko pehle try karo; baaki supported models fallback hain.
        candidates = list(dict.fromkeys(candidates))
        candidates.sort(key=lambda name: ("flash" not in name.lower(), name))

        # Listing unavailable ho to known IDs fallback ke roop mein try honge.
        if not candidates:
            candidates = ["gemini-3.8-flash", "gemini-2.5-flash"]

        last_error = None
        quota_error = None
        for model_name in candidates[:6]:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )
                answer = getattr(response, "text", None)
                if answer and str(answer).strip():
                    return str(answer).strip()
                last_error = Exception("Gemini returned an empty response.")
            except Exception as e:
                last_error = e
                error_text = str(e).lower()

                if any(term in error_text for term in [
                    "api key not valid", "api_key_invalid", "invalid api key"
                ]):
                    return (
                        "Gemini API key invalid hai. Google AI Studio mein key "
                        "check karke .streamlit/secrets.toml mein update karo. "
                        "API key kisi ke saath share mat karna."
                    )

                if "429" in error_text or "resource_exhausted" in error_text or "quota" in error_text:
                    quota_error = e
                    # Ek model ki limit hit ho to available next model try karo.
                    continue

                if "404" in error_text or "not found" in error_text:
                    continue

                if any(term in error_text for term in ["503", "unavailable", "high demand", "overloaded", "500", "504"]):
                    time.sleep(2)
                    continue

                # Model-specific error par agla supported model try karo.
                continue

        if quota_error is not None:
            detail = str(quota_error).replace("\n", " ")[:220]
            return (
                "Gemini API ne request ko quota/rate limit ki wajah se reject kiya. "
                "Code ab available fallback models bhi try karta hai, lekin agar "
                "poore Google project ki quota khatam hai to koi model response "
                "nahi dega.\n\nTechnical detail: " + detail
            )

        if last_error is not None:
            detail = str(last_error).replace("\n", " ")[:250]
            return (
                "Gemini se response nahi mila.\n\nTechnical detail: "
                + type(last_error).__name__ + ": " + detail
            )

        return "Is API key ke liye koi supported Gemini model nahi mila."

    except Exception as e:
        return (
            "Chatbot mein connection error aaya.\n\nTechnical detail: "
            + type(e).__name__ + ": " + str(e).replace("\n", " ")[:250]
        )


# ==================== DESIGN ====================

st.markdown("""
<style>

.stApp {
    background:
        radial-gradient(
            circle at 12% 8%,
            rgba(59,178,218,.28),
            transparent 30%
        ),
        radial-gradient(
            circle at 88% 18%,
            rgba(91,113,220,.24),
            transparent 28%
        ),
        linear-gradient(
            135deg,
            #06152e 0%,
            #102f55 48%,
            #123f63 100%
        );

    color:#f7fbff;
}

[data-testid="stHeader"] {
    background:rgba(5,20,42,.55);
}

[data-testid="stSidebar"] {
    background:linear-gradient(
        180deg,
        #0b2342,
        #123b5d
    );
}

h1,h2,h3,h4,p,label,
.stMarkdown,
[data-testid="stCaptionContainer"] {
    color:#f7fbff !important;
}

[data-testid="stTabs"] button {
    color:#eaf7ff !important;
    font-weight:700;
    font-size:17px;
}

[data-testid="stVerticalBlockBorderWrapper"] {
    background:rgba(255,255,255,.075);
    border:1px solid rgba(151,218,245,.24);
    border-radius:16px;
    padding:14px;
}

.stTextInput input,
.stTextArea textarea,
.stNumberInput input,
[data-baseweb="select"] > div {
    background-color:#fff !important;
    color:#14243a !important;
    border-radius:9px !important;
    font-size:16px !important;
}

.stButton button,
.stFormSubmitButton button {
    background:linear-gradient(
        90deg,
        #55c5e5,
        #8be0ed
    ) !important;

    color:#08213d !important;
    border:0 !important;
    border-radius:10px !important;
    font-weight:750 !important;
    font-size:16px !important;
    min-height:42px;
}

.medicine-photo-placeholder {
    width:100%;
    min-height:145px;
    border-radius:12px;
    display:flex;
    flex-direction:column;
    align-items:center;
    justify-content:center;
    text-align:center;
    background:rgba(255,255,255,.12);
    color:#d9f3ff;
    border:1px dashed rgba(190,230,250,.5);
    font-size:34px;
}

.medicine-photo-placeholder span {
    font-size:12px;
    margin-top:5px;
}

[data-testid="stImage"] img {
    border-radius:12px;
    object-fit:contain;
}

hr {
    border-color:rgba(220,245,255,.22) !important;
}

</style>
""", unsafe_allow_html=True)


# ==================== SESSION STATE ====================

if "user" not in st.session_state:
    st.session_state.user = None

if "chat" not in st.session_state:
    st.session_state.chat = []

if "otp_email" not in st.session_state:
    st.session_state.otp_email = None


st.title("💊 PharmaPath")
st.caption("Medicine Availability & Pharmacy Finder")


# ==================== LOGGED IN DASHBOARD ====================

if st.session_state.user:

    user = st.session_state.user

    col1, col2 = st.columns([5, 1])

    with col1:
        st.write(f"Welcome, **{user[1]}**")

    with col2:
        if st.button("Logout"):
            st.session_state.user = None
            st.session_state.chat = []
            st.rerun()

    st.divider()

    # ==================== SHOPKEEPER ====================

    if str(user[4]).lower() == "shopkeeper":

        inventory_tab, add_tab, bot_tab = st.tabs([
            "📦 My Inventory",
            "➕ Add Medicine",
            "💬 Chatbot"
        ])

        # INVENTORY

        with inventory_tab:

            st.subheader("My Medicines")

            medicines = get_medicines(user[0])

            if not medicines:
                st.info("Your inventory is empty.")

            for medicine in medicines:

                mid, name, qty, price, photo = medicine

                with st.container(border=True):

                    c1, c2 = st.columns([1, 3])

                    with c1:
                        display_medicine_photo(
                            photo,
                            width=180
                        )

                    with c2:
                        st.markdown(f"**{name}**")
                        st.write(f"Quantity: {qty}")
                        st.write(f"Price: ₹{price:.2f}")

                        st.write(
                            "Available"
                            if qty > 0
                            else "Out of stock"
                        )

                    with st.expander("Edit / Delete"):

                        with st.form(f"edit_{mid}"):

                            new_name = st.text_input(
                                "Medicine name",
                                value=name,
                                key=f"name{mid}"
                            )

                            new_qty = st.number_input(
                                "Quantity",
                                min_value=0,
                                value=int(qty),
                                key=f"qty{mid}"
                            )

                            new_price = st.number_input(
                                "Price",
                                min_value=0.0,
                                value=float(price),
                                key=f"price{mid}"
                            )

                            new_photo = st.file_uploader(
                                "Change photo",
                                type=["png", "jpg", "jpeg"],
                                key=f"photo{mid}"
                            )

                            if st.form_submit_button(
                                "Update Medicine"
                            ):

                                photo_data = (
                                    new_photo.getvalue()
                                    if new_photo
                                    else photo
                                )

                                if new_name.strip():

                                    update_medicine(
                                        mid,
                                        user[0],
                                        new_name,
                                        new_qty,
                                        new_price,
                                        photo_data
                                    )

                                    st.success(
                                        "Medicine updated!"
                                    )

                                    st.rerun()

                        confirm = st.checkbox(
                            "Confirm deletion",
                            key=f"confirm{mid}"
                        )

                        if st.button(
                            "Delete Medicine",
                            key=f"delete{mid}",
                            disabled=not confirm
                        ):

                            delete_medicine(
                                mid,
                                user[0]
                            )

                            st.success(
                                "Medicine deleted!"
                            )

                            st.rerun()

        # ADD MEDICINE

        with add_tab:

            st.subheader("Add New Medicine")

            with st.form(
                "add_form",
                clear_on_submit=True
            ):

                name = st.text_input(
                    "Medicine name"
                )

                qty = st.number_input(
                    "Quantity",
                    min_value=0,
                    value=1
                )

                price = st.number_input(
                    "Price (₹)",
                    min_value=0.0
                )

                photo = st.file_uploader(
                    "Select photo from gallery",
                    type=["png", "jpg", "jpeg"]
                )

                submitted = st.form_submit_button(
                    "Add Medicine"
                )

                if submitted:

                    if not name.strip():
                        st.error(
                            "Medicine name is required."
                        )

                    else:

                        add_medicine(
                            user[0],
                            name,
                            qty,
                            price,
                            photo.getvalue() if photo else None
                        )

                        st.success(
                            "Medicine added successfully!"
                        )

        # SHOPKEEPER CHATBOT

        with bot_tab:

            st.subheader("💬 Medicine Assistant")

            for msg in st.session_state.chat:

                with st.chat_message(msg["role"]):
                    st.write(msg["content"])

            question = st.chat_input(
                "Ask about a medicine..."
            )

            if question:

                st.session_state.chat.append({
                    "role": "user",
                    "content": question
                })

                with st.spinner(
                    "PharmaPath is thinking..."
                ):

                    answer = chatbot(
                        question,
                        st.session_state.chat
                    )

                st.session_state.chat.append({
                    "role": "assistant",
                    "content": answer
                })

                st.rerun()

    # ==================== CONSUMER ====================

    else:

        search_tab, bot_tab = st.tabs([
            "🔎 Find Medicine",
            "💬 Medicine Assistant"
        ])

        # MEDICINE SEARCH

        with search_tab:

            st.subheader(
                "Find Medicines Near You"
            )

            area = st.text_input(
                "Enter your area / locality",
                value=user[6] or ""
            )

            search = st.text_input(
                "Search medicine name"
            )

            if st.button("Search Medicines"):

                if not area.strip():

                    st.error(
                        "Please enter your area first."
                    )

                else:

                    con = connect()

                    results = con.execute("""
                    SELECT
                        m.name,
                        m.quantity,
                        m.price,
                        COALESCE(NULLIF(m.photo,X''),m.image),
                        u.shop_name,
                        u.area,
                        u.email
                    FROM medicines m
                    JOIN users u
                    ON m.user_id=u.id
                    WHERE lower(u.area) LIKE ?
                    AND lower(m.name) LIKE ?
                    ORDER BY m.name
                    """, (
                        "%" + area.strip().lower() + "%",
                        "%" + search.strip().lower() + "%"
                    )).fetchall()

                    con.close()

                    st.session_state.results = results

            if "results" in st.session_state:

                results = st.session_state.results

                if not results:
                    st.warning(
                        "No matching medicines found."
                    )

                for medicine in results:

                    (
                        name,
                        qty,
                        price,
                        photo,
                        shop,
                        shop_area,
                        email
                    ) = medicine

                    with st.container(border=True):

                        c1, c2 = st.columns([1, 3])

                        with c1:
                            display_medicine_photo(
                                photo,
                                width=180
                            )

                        with c2:

                            st.markdown(
                                f"**{name}**"
                            )

                            st.write(
                                f"Pharmacy: {shop or 'Shopkeeper'}"
                            )

                            st.write(
                                f"Area: {shop_area}"
                            )

                            st.write(
                                f"Price: ₹{price:.2f}"
                            )

                            st.write(
                                "Available"
                                if qty > 0
                                else "Out of stock"
                            )

                            st.write(
                                f"Contact: {email}"
                            )

        # CONSUMER CHATBOT

        with bot_tab:

            st.subheader(
                "💬 Medicine Assistant"
            )

            for msg in st.session_state.chat:

                with st.chat_message(msg["role"]):
                    st.write(msg["content"])

            question = st.chat_input(
                "What is Dolo? Ask about medicines..."
            )

            if question:

                st.session_state.chat.append({
                    "role": "user",
                    "content": question
                })

                with st.spinner(
                    "PharmaPath is thinking..."
                ):

                    answer = chatbot(
                        question,
                        st.session_state.chat
                    )

                st.session_state.chat.append({
                    "role": "assistant",
                    "content": answer
                })

                st.rerun()


# ==================== LOGIN / SIGNUP ====================

else:

    login_tab, signup_tab, forgot_tab = st.tabs([
        "🔐 Login",
        "📝 Signup",
        "🔑 Forgot Password"
    ])

    # LOGIN

    with login_tab:

        st.subheader(
            "Login to PharmaPath"
        )

        role = st.radio(
            "Login as",
            ["Consumer", "Shopkeeper"],
            horizontal=True
        )

        email = st.text_input(
            "Email"
        )

        password = st.text_input(
            "Password",
            type="password"
        )

        if st.button(
            "Login",
            use_container_width=True
        ):

            account = get_user(email)

            if not account:

                st.error(
                    "Account not found. Please check your email."
                )

            else:

                valid, upgrade = verify_password(
                    password,
                    account[3]
                )

                if not valid:

                    st.error(
                        "Incorrect email or password."
                    )

                elif str(account[4]).lower() != role.lower():

                    st.error(
                        f"This account is registered as "
                        f"{str(account[4]).title()}. "
                        "Please select the correct login type."
                    )

                else:

                    if upgrade:

                        new_hash = hash_password(
                            password
                        )

                        con = connect()

                        con.execute("""
                        UPDATE users
                        SET password=?,password_hash=?
                        WHERE id=?
                        """, (
                            new_hash,
                            new_hash,
                            account[0]
                        ))

                        con.commit()
                        con.close()

                    st.session_state.user = account
                    st.rerun()

    # SIGNUP

    with signup_tab:

        st.subheader(
            "Create Account"
        )

        role = st.radio(
            "Choose account type",
            ["Consumer", "Shopkeeper"],
            horizontal=True,
            key="signup_role"
        )

        with st.form("signup_form"):

            name = st.text_input(
                "Full Name"
            )

            email = st.text_input(
                "Email Address"
            )

            password = st.text_input(
                "Create Password",
                type="password"
            )

            confirm = st.text_input(
                "Confirm Password",
                type="password"
            )

            shop = ""
            area = ""

            if role == "Shopkeeper":

                shop = st.text_input(
                    "Shop Name"
                )

                area = st.text_input(
                    "Shop Area"
                )

            submit = st.form_submit_button(
                "Create Account"
            )

            if submit:

                if (
                    not name.strip()
                    or not email.strip()
                    or not password
                ):

                    st.error(
                        "Please fill all required fields."
                    )

                elif "@" not in email or "." not in email:

                    st.error(
                        "Enter a valid email."
                    )

                elif len(password) < 6:

                    st.error(
                        "Password must have at least 6 characters."
                    )

                elif password != confirm:

                    st.error(
                        "Passwords do not match."
                    )

                elif role == "Shopkeeper" and (
                    not shop.strip()
                    or not area.strip()
                ):

                    st.error(
                        "Shop name and area are required."
                    )

                else:

                    success, message = register(
                        name,
                        email,
                        password,
                        role.lower(),
                        shop,
                        area
                    )

                    if success:

                        st.success(
                            "Account created! Please login."
                        )

                    else:

                        st.error(message)

    # FORGOT PASSWORD OTP

    with forgot_tab:

        st.subheader(
            "Reset Password with OTP"
        )

        reset_email = st.text_input(
            "Registered email address"
        )

        if st.button("Send OTP"):

            account = get_user(reset_email)

            if not account:

                st.error(
                    "Email not registered."
                )

            else:

                try:

                    sender = st.secrets.get(
                        "PHARMAPATH_EMAIL",
                        os.getenv(
                            "PHARMAPATH_EMAIL",
                            ""
                        )
                    )

                    app_password = st.secrets.get(
                        "PHARMAPATH_EMAIL_PASSWORD",
                        os.getenv(
                            "PHARMAPATH_EMAIL_PASSWORD",
                            ""
                        )
                    )

                except Exception:

                    sender = os.getenv(
                        "PHARMAPATH_EMAIL",
                        ""
                    )

                    app_password = os.getenv(
                        "PHARMAPATH_EMAIL_PASSWORD",
                        ""
                    )

                if not sender or not app_password:

                    st.error(
                        "Gmail OTP configuration is required."
                    )

                else:

                    otp = str(
                        random.randint(100000, 999999)
                    )

                    msg = EmailMessage()

                    msg["Subject"] = (
                        "PharmaPath Password Reset OTP"
                    )

                    msg["From"] = sender
                    msg["To"] = reset_email

                    msg.set_content(
                        f"Your PharmaPath OTP is {otp}. "
                        "It expires in 5 minutes."
                    )
                    try:

                         with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as server:

                          server.ehlo()
                          server.starttls()
                          server.ehlo()

                          server.login(
                          sender.strip(),
                          app_password.strip().replace(" ", "")
                                 )

                          server.send_message(msg)

                        st.session_state.otp_email = (
                            reset_email.lower()
                        )

                        st.session_state.reset_otp = otp

                        st.session_state.otp_expiry = (
                            time.time() + 300
                        )

                        st.success(
                            "OTP sent to your email."
                        )

                    except Exception as e:

                        st.error(
                            "OTP could not be sent. " + str(e)
                        )

        if st.session_state.otp_email:

            entered = st.text_input(
                "Enter OTP"
            )

            new_password = st.text_input(
                "New Password",
                type="password"
            )

            confirm_password = st.text_input(
                "Confirm New Password",
                type="password"
            )

            if st.button("Reset Password"):

                if time.time() > st.session_state.otp_expiry:

                    st.error(
                        "OTP expired. Send a new OTP."
                    )

                elif entered != st.session_state.reset_otp:

                    st.error(
                        "Incorrect OTP."
                    )

                elif len(new_password) < 6:

                    st.error(
                        "Password must have at least 6 characters."
                    )

                elif new_password != confirm_password:

                    st.error(
                        "Passwords do not match."
                    )

                else:

                    new_hash = hash_password(
                        new_password
                    )

                    con = connect()

                    con.execute("""
                    UPDATE users
                    SET password=?,password_hash=?
                    WHERE lower(email)=?
                    """, (
                        new_hash,
                        new_hash,
                        st.session_state.otp_email
                    ))

                    con.commit()
                    con.close()

                    st.session_state.otp_email = None
                    st.session_state.pop(
                        "reset_otp",
                        None
                    )

                    st.success(
                        "Password changed successfully. Login now."
                    )


# ==================== FOOTER ====================

st.divider()

st.caption(
    "PharmaPath provides general medicine information only. "
    "Always consult a qualified doctor or pharmacist before using medicines."
)
