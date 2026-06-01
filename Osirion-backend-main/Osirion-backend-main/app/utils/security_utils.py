from cryptography.fernet import Fernet
import os
from dotenv import load_dotenv

load_dotenv()  # charge le fichier .env
key = os.getenv("FERNET_KEY")
cipher = Fernet(key)

def crypter(texte):
    return cipher.encrypt(texte.encode()).decode()

def decrypter(token):
    return cipher.decrypt(token.encode()).decode()

