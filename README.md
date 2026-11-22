# PharmaPath

Medicine Availability & Pharmacy Finder — Consumer aur Shopkeeper ke liye.

## Features (sirf finalised requirements)
- Consumer aur Shopkeeper Sign Up / Login
- Shopkeeper: shop name aur area save kare
- Shopkeeper: medicine name, quantity, price aur photo add/update kare
- Photo camera se click ya gallery se upload ho sakti hai
- Quantity 0 hone par status Out of Stock dikhega
- Consumer: area enter karke shops aur medicines dekhe
- Consumer: medicine name search karke photo, quantity, price aur status dekhe

## Step 1: ZIP extract karo
ZIP ko extract karke `PharmaPath` folder open karo.

## Step 2: VS Code mein folder open karo
VS Code > File > Open Folder > `PharmaPath`.

## Step 3: Python check karo
VS Code terminal mein:
```bash
py --version
```
Agar Python version aa raha hai, next step karo.

## Step 4: Virtual environment (recommended)
Windows terminal:
```bash
py -m venv venv
venv\Scripts\activate
```

## Step 5: Packages install karo
```bash
py -m pip install -r requirements.txt
```

## Step 6: Website run karo
```bash
py -m streamlit run app.py
```
Browser mein local website open ho jayegi. Terminal mein diya URL (usually http://localhost:8501) open karo.

## Step 7: Test karo
1. Sign Up tab mein Shopkeeper account banao. Shop name aur area fill karo.
2. Login tab mein Shopkeeper select karke login karo.
3. Medicine name, quantity, price aur camera/gallery photo add karke Save Medicine dabao.
4. Logout karo.
5. Consumer account Sign Up karo aur Consumer ke roop mein login karo.
6. Apna area enter karo. Medicine name optional hai. Find Shops dabao.
7. Stock khatam karne ke liye Shopkeeper login karke us medicine ki quantity 0 save karo. Consumer ko Out of Stock dikhega.

## Step 8: GitHub par upload
1. GitHub par new repository banao: `PharmaPath`.
2. `app.py`, `requirements.txt`, `README.md` upload karo.
3. `venv` folder upload mat karna.
4. `pharmapath.db` local testing ke baad GitHub par upload mat karna; usmein test accounts aur inventory ho sakti hai.

## Step 9: Streamlit Cloud par deploy
1. https://share.streamlit.io/ open karo.
2. GitHub se sign in karo.
3. Create app select karo.
4. Repository `PharmaPath`, branch `main`, main file `app.py` select karo.
5. Deploy dabao.

## Important deployment note
Is starter version mein SQLite database app ke local folder mein banta hai. Streamlit Community Cloud par local files persistent database ki tarah guaranteed nahi hoti; app restart/redeploy par demo data reset ho sakta hai. College demo ke liye theek hai, lekin real public use se pehle persistent hosted database/storage lagana hoga.

## Notes
- New medicine add karte waqt photo required hai. Existing medicine ko update karte waqt photo dobara dena zaroori nahi; purani photo rahegi.
- Same shop mein same medicine name dobara save karne par nayi row banane ke bajay quantity, price aur (agar nayi photo di ho) photo update hogi.
- Consumer ka area search shopkeeper ke entered area ke text se match hota hai; yeh GPS-based distance search nahi hai.


## Medicine Assistant chatbot
The chatbot is rule-based and runs locally in Python. It does not call a paid AI API and does not need an API key. It gives limited general information and directs users to a doctor/pharmacist for personal dosing or medical decisions. It is not a diagnostic or prescription tool.
