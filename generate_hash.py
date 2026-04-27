import hashlib

name = input("Student Name: ")
course = input("Course: ")
institution = input("Institution: ")
year = input("Year: ")
percentage = input("Percentage: ")

data = name + course + institution + year + percentage

hash_value = hashlib.sha256(data.encode()).hexdigest()

print("\nCertificate Hash:")
print(hash_value)
