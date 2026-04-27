import qrcode

cert_hash = input("Enter Certificate Hash: ")

qr = qrcode.make(cert_hash)
qr.save("certificate_qr.png")

print("QR Code generated: certificate_qr.png")
