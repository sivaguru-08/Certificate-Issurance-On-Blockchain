from flask import (
    Flask, request, render_template,
    redirect, session, send_file
)
from web3 import Web3
from werkzeug.security import check_password_hash
from flask_mail import Mail, Message
import ipfshttpclient
import json, os, qrcode, uuid
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from datetime import datetime

from database import get_db, CERT_COLLECTION, HISTORY_COLLECTION, ADMINS_COLLECTION

# ================= APP SETUP =================
app = Flask(__name__)
app.secret_key = "supersecretkey"

BASE_URL = "http://127.0.0.1:5000"

# ================= BLOCKCHAIN =================
CONTRACT_ADDRESS = "0xA8fd41DeFFE9B60C9dbC9FCC5CE638821b6366BE"
BLOCKCHAIN_CONNECTED = False
contract = None

try:
    web3 = Web3(Web3.HTTPProvider("http://127.0.0.1:7545"))
    if web3.is_connected():
        web3.eth.default_account = web3.eth.accounts[0]
        with open("abi.json", "r") as f:
            ABI = json.load(f)
        contract = web3.eth.contract(address=CONTRACT_ADDRESS, abi=ABI)
        code = web3.eth.get_code(CONTRACT_ADDRESS)
        if code.hex() in ["0x", ""]:
            print(f"⚠ Warning: No contract code found at {CONTRACT_ADDRESS}. Redeployment may be needed.")
            BLOCKCHAIN_CONNECTED = False
        else:
            BLOCKCHAIN_CONNECTED = True
    else:
        BLOCKCHAIN_CONNECTED = False
        print("⚠ Blockchain Error: Could not connect to Ganache on http://127.0.0.1:7545")
except Exception as e:
    print(f"⚠ Blockchain Error: {e}")
    BLOCKCHAIN_CONNECTED = False
    contract = None

# ================= EMAIL CONFIG =================
app.config.update(
    MAIL_SERVER="smtp.gmail.com",
    MAIL_PORT=587,
    MAIL_USE_TLS=True,
    MAIL_USERNAME="sivaguru.081206@gmail.com",
    MAIL_PASSWORD="Siva@96385207410"
)
mail = Mail(app)

# ================= HELPERS =================
def calculate_grade_and_class(p):
    p = float(p)
    if p >= 85: return "A", "First Class with Distinction"
    if p >= 70: return "B", "First Class"
    if p >= 60: return "C", "Second Class"
    if p >= 50: return "D", "Pass"
    return "F", "Fail"

def save_history(cert_hash, status):
    db = get_db()
    record = {
        "hash": cert_hash,
        "status": "Valid" if status else "Invalid",
        "time": datetime.now().strftime("%d-%m-%Y %H:%M:%S")
    }
    if db is not None:
        db[HISTORY_COLLECTION].insert_one(record)
    else:
        print("⚠ MongoDB unavailable: history not saved.")

def upload_to_ipfs(path):
    try:
        client = ipfshttpclient.connect(
            "/ip4/127.0.0.1/tcp/5001", timeout=5
        )
        res = client.add(path)
        return res["Hash"]
    except Exception as e:
        print("⚠ IPFS skipped:", e)
        return None

def send_certificate_email(student_email, cert_hash, student_name, course_name):
    if not student_email: return False
    try:
        msg = Message(
            "Certificate Issued - Blockchain Secured",
            sender=app.config.get("MAIL_USERNAME"),
            recipients=[student_email]
        )
        msg.body = (
            f"Hello {student_name},\n\n"
            f"Your certificate for {course_name} has been issued.\n\n"
            f"Hash: {cert_hash}\n"
            f"Verify here: {BASE_URL}/verifier\n\n"
            f"Best regards,\nCertification Team"
        )
        mail.send(msg)
        return True
    except Exception as e:
        print(f"⚠ Email Error: {e}")
        return False

# ================= PDF =================
def generate_certificate_pdf(student, cert_hash, issued_at, issuer):
    os.makedirs("static", exist_ok=True)
    path = "static/certificate.pdf"

    c = canvas.Canvas(path, pagesize=A4)
    w, h = A4

    c.setLineWidth(4)
    c.rect(30, 30, w-60, h-60)

    if os.path.exists("static/logo.png"):
        c.drawImage("static/logo.png", w/2-120, h-150, 240, 80)

    c.setFont("Helvetica-Bold", 26)
    c.drawCentredString(w/2, h-220, "CERTIFICATE OF COMPLETION")

    c.setFont("Helvetica", 14)
    c.drawCentredString(w/2, h-260, "This is to certify that")

    c.setFont("Helvetica-Bold", 22)
    c.drawCentredString(w/2, h-300, student["name"])

    c.setFont("Helvetica", 14)
    c.drawCentredString(w/2, h-335, "has successfully completed the course")

    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(w/2, h-365, student["course"])

    c.setFont("Helvetica", 14)
    c.drawCentredString(w/2, h-395, f"at {student['institution']}")
    c.drawCentredString(w/2, h-420, f"Year: {student['year']}")

    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(w/2, h-455, f"Percentage: {student['percentage']}%")
    c.drawCentredString(
        w/2, h-480,
        f"Grade: {student['grade']} | Class: {student['class']}"
    )

    c.line(100, h-520, w-100, h-520)

    c.setFont("Helvetica", 10)
    c.drawString(100, h-550, f"Certificate Hash: {cert_hash}")
    c.drawString(100, h-565, f"Issuer: {issuer}")
    c.drawString(100, h-580, f"Issued At: {issued_at}")

    c.drawCentredString(w/2, 120, "Verified & Secured using Blockchain")

    c.showPage()
    c.save()
    return path

# ================= USER =================
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/verify", methods=["POST"])
def verify():
    if not BLOCKCHAIN_CONNECTED:
        return render_template("index.html", result={"error": "Blockchain connection offline"})

    cert_hash = request.form["hash"]
    try:
        valid, issued_at, issuer = contract.functions.verifyCertificate(cert_hash).call()
    except Exception as e:
        error_msg = str(e)
        if "Could not transact" in error_msg or "is contract deployed correctly" in error_msg:
            error_msg = "Contract not found. Please ensure Ganache is running and the contract is deployed."
        elif "Failed to connect" in error_msg:
            error_msg = "Lost connection to Ganache. Please restart Ganache."
        return render_template("index.html", result={"error": f"Verification failed: {error_msg}"})

    save_history(cert_hash, valid)

    if valid:
        download_url = f"{BASE_URL}/download/{cert_hash}"
        qrcode.make(download_url).save("static/qr.png")

    return render_template(
        "index.html",
        result={"valid": valid, "issuer": issuer, "hash": cert_hash}
    )

@app.route("/download", methods=["POST"])
def download():
    cert_hash = request.form.get("hash")
    return process_download(cert_hash)

@app.route("/download/<cert_hash>")
def download_link(cert_hash):
    return process_download(cert_hash)

def process_download(cert_hash):
    if not cert_hash:
        return "Error: No hash provided"

    if not BLOCKCHAIN_CONNECTED:
        return "Error: Blockchain connection offline. Cannot verify certificate for download."

    try:
        valid, issued_at, issuer = contract.functions.verifyCertificate(cert_hash).call()
    except Exception as e:
        return f"Error: Blockchain verification failed: {e}"

    if not valid:
        return "Invalid Certificate"

    db = get_db()
    if db is None:
        return "Error: Database unavailable."

    student = db[CERT_COLLECTION].find_one({"hash": cert_hash})
    if not student:
        return "Student data missing"

    # If a PDF was previously saved, return it
    if student.get("pdf_path") and os.path.exists(student["pdf_path"]):
        return send_file(
            student["pdf_path"],
            as_attachment=True,
            download_name="Blockchain_Certificate.pdf"
        )

    # Otherwise generate a new one
    pdf_path = generate_certificate_pdf(student, cert_hash, issued_at, issuer)

    # Optional IPFS upload
    if not student.get("ipfs"):
        ipfs_hash = upload_to_ipfs(pdf_path)
        if ipfs_hash:
            db[CERT_COLLECTION].update_one(
                {"hash": cert_hash},
                {"$set": {"ipfs": ipfs_hash}}
            )

    return send_file(
        pdf_path,
        as_attachment=True,
        download_name="Blockchain_Certificate.pdf"
    )

# ================= ADMIN =================
@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]

        db = get_db()
        if db is not None:
            admin_doc = db[ADMINS_COLLECTION].find_one({"username": u})
            if admin_doc and check_password_hash(admin_doc["password"], p):
                session["admin"] = True
                return redirect("/issue")

    return render_template("admin.html")

@app.route("/issue", methods=["GET", "POST"])
def issue():
    if not session.get("admin"):
        return redirect("/admin")

    msg = ""
    if request.method == "POST":
        try:
            cert_hash = str(uuid.uuid4())

            # 1. Blockchain Issue
            if not BLOCKCHAIN_CONNECTED:
                return render_template("admin.html", message="Error: Blockchain connection offline.")

            try:
                tx = contract.functions.issueCertificate(cert_hash).transact()
                web3.eth.wait_for_transaction_receipt(tx)
            except Exception as e:
                print(f"Blockchain Error: {e}")
                return render_template("admin.html", message=f"Error: Blockchain Transaction Failed. {e}")

            # 2. Grade Calculation
            try:
                grade, cls = calculate_grade_and_class(request.form["percentage"])
            except ValueError:
                grade, cls = "N/A", "N/A"

            # 3. Handle PDF Upload
            pdf_path = ""
            if "certificate_pdf" in request.files:
                file = request.files["certificate_pdf"]
                if file.filename != "":
                    try:
                        os.makedirs("static/uploads", exist_ok=True)
                        clean_hash = "".join(x for x in cert_hash if x.isalnum())
                        if not clean_hash: clean_hash = "unknown"
                        pdf_path = f"static/uploads/{clean_hash}.pdf"
                        file.save(pdf_path)
                    except Exception as e:
                        print(f"File Save Error: {e}")

            # 4. Save to MongoDB
            certificate_data = {
                "hash": cert_hash,
                "name": request.form["name"],
                "course": request.form["course"],
                "institution": request.form["institution"],
                "year": request.form["year"],
                "percentage": request.form["percentage"],
                "grade": grade,
                "class": cls,
                "cgpa": request.form.get("cgpa", "N/A"),
                "email": request.form.get("email", ""),
                "pdf_path": pdf_path
            }

            db = get_db()
            if db is not None:
                db[CERT_COLLECTION].update_one(
                    {"hash": cert_hash},
                    {"$set": certificate_data},
                    upsert=True
                )
            else:
                return render_template("admin.html", message="Error: Database unavailable.")

            # 5. Send Email
            if request.form.get("email"):
                send_certificate_email(
                    request.form["email"],
                    cert_hash,
                    request.form["name"],
                    request.form["course"]
                )

            msg = "Certificate Issued & Email Sent Successfully"
            return render_template("admin.html", message=msg, issued_hash=cert_hash)

        except Exception as e:
            print(f"General Error: {e}")
            msg = f"Error: {str(e)}"

    return render_template("admin.html", message=msg)

# ================= DASHBOARD =================
@app.route("/dashboard")
def dashboard():
    if not session.get("admin"):
        return redirect("/admin")

    db = get_db()
    if db is None:
        return render_template("dashboard.html",
            total_certificates=0, total_verifications=0, valid=0, invalid=0)

    total_certificates = db[CERT_COLLECTION].count_documents({})
    total_verifications = db[HISTORY_COLLECTION].count_documents({})
    valid = db[HISTORY_COLLECTION].count_documents({"status": "Valid"})
    invalid = db[HISTORY_COLLECTION].count_documents({"status": "Invalid"})

    return render_template(
        "dashboard.html",
        total_certificates=total_certificates,
        total_verifications=total_verifications,
        valid=valid,
        invalid=invalid
    )

# ================= VERIFIER =================
@app.route("/verifier", methods=["GET", "POST"])
def verifier():
    result = None
    if request.method == "POST":
        cert_hash = request.form["hash"]

        if not BLOCKCHAIN_CONNECTED:
            return render_template("verifier.html", result={"error": "Blockchain connection offline"})

        try:
            valid, issued_at, issuer = contract.functions.verifyCertificate(cert_hash).call()
        except Exception as e:
            error_msg = str(e)
            if "Could not transact" in error_msg:
                error_msg = "Contract or connection issue. Ensure Ganache is running."
            return render_template("verifier.html", result={"error": f"Error: {error_msg}"})

        if valid:
            db = get_db()
            student = None
            if db is not None:
                student = db[CERT_COLLECTION].find_one({"hash": cert_hash})
            result = {
                "valid": True,
                "student": student,
                "issuer": issuer,
                "issued_at": datetime.fromtimestamp(int(issued_at)).strftime("%d-%m-%Y")
            }
        else:
            result = {"valid": False}

    return render_template("verifier.html", result=result)

# ================= HISTORY =================
@app.route("/history")
def history():
    db = get_db()
    records = []
    if db is not None:
        records = list(db[HISTORY_COLLECTION].find({}, {"_id": 0}).sort("time", -1))
    return render_template("history.html", records=records)

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ================= RUN =================
if __name__ == "__main__":
    app.run(debug=True)
