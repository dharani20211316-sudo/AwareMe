from werkzeug.security import generate_password_hash

hashed_pw = generate_password_hash("123")
print(hashed_pw)
