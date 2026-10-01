from cryptography.fernet import Fernet
import os
from dotenv import load_dotenv

load_dotenv()  # charge le fichier .env
key = os.getenv("FERNET_KEY")
cipher = Fernet(key)

def crypter(texte):
    return cipher.encrypt(texte.encode()).decode()

def decrypter(token):
    # Les caméras HikCentral n'ont pas de rtsp_url stockée (résolue à la demande) :
    # rtsp_url = NULL en base → on renvoie None plutôt que de planter sur None.encode().
    if not token:
        return None
    return cipher.decrypt(token.encode()).decode()

