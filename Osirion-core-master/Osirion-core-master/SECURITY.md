# 🔒 GUIDE DE SÉCURITÉ - OSIRION-CORE

## ✅ Problèmes résolus

### 1. Secret Flask hardcodé
**Avant** : Secret en dur dans le code → Session hijacking possible
```python
# ❌ DANGEREUX
self.app.config['SECRET_KEY'] = 'osirion-surveillance-2026'
```

**Maintenant** : Secret depuis variable d'environnement
```python
# ✅ SÉCURISÉ
FLASK_SECRET_KEY = os.getenv('FLASK_SECRET_KEY', secrets.token_hex(32))
```

### 2. CORS trop permissif
**Avant** : N'importe quel site web peut accéder aux flux
```python
# ❌ DANGEREUX
self.socketio = SocketIO(app, cors_allowed_origins="*")
```

**Maintenant** : Liste d'origines autorisées configurable
```python
# ✅ SÉCURISÉ
CORS_ALLOWED_ORIGINS = os.getenv('CORS_ALLOWED_ORIGINS', '*').split(',')
self.socketio = SocketIO(app, cors_allowed_origins=CORS_ALLOWED_ORIGINS)
```

---

## 🚀 Configuration de production

### 1. Générer un secret Flask sécurisé
```bash
# Windows PowerShell
python -c "import secrets; print(secrets.token_hex(32))"

# Exemple de résultat :
# a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2
```

### 2. Configurer le fichier .env
```bash
# Copier le template
copy .env.example .env

# Éditer .env et remplacer :
FLASK_SECRET_KEY=VOTRE_SECRET_GENERE_ICI
CORS_ALLOWED_ORIGINS=https://votre-domaine.com,https://app.votre-domaine.com
```

### 3. Vérifier la configuration
```python
# Au démarrage, vous verrez :
[WARN] CORS configuré pour accepter toutes les origines (mode développement)
[WARN] En production, définir CORS_ALLOWED_ORIGINS dans .env

# En production, ce message ne doit PAS apparaître
```

---

## 📋 Checklist de sécurité

### Avant déploiement
- [ ] `FLASK_SECRET_KEY` généré aléatoirement (32+ caractères)
- [ ] `CORS_ALLOWED_ORIGINS` restreint aux domaines autorisés
- [ ] `debug=False` dans .env
- [ ] Fichier `.env` ajouté au `.gitignore` (ne JAMAIS commit)
- [ ] HTTPS activé (recommandé pour production)
- [ ] Firewall configuré (limiter l'accès au port 5000)

### Recommandations supplémentaires
- [ ] Ajouter authentification JWT sur WebSocket (prochaine étape)
- [ ] Implémenter rate limiting (limiter connexions/IP)
- [ ] Activer HTTPS avec certificat SSL/TLS
- [ ] Monitoring des connexions suspectes
- [ ] Logs sécurisés (ne pas logger les tokens)

---

## 🔐 Niveaux de sécurité

### Niveau 1 : Développement local
```bash
CORS_ALLOWED_ORIGINS=*
FLASK_SECRET_KEY=dev-secret-key-123
```
✅ Acceptable pour tester en local

### Niveau 2 : Réseau privé (LAN)
```bash
CORS_ALLOWED_ORIGINS=http://192.168.1.100:3000,http://192.168.1.101:8080
FLASK_SECRET_KEY=<secret-généré-32-chars>
```
✅ Bon pour environnement de test interne

### Niveau 3 : Production Internet
```bash
CORS_ALLOWED_ORIGINS=https://app.votredomaine.com
FLASK_SECRET_KEY=<secret-généré-64-chars>
```
✅ + HTTPS + JWT Authentication + Rate Limiting

---

## 🚨 En cas de compromission

Si vous pensez que votre `FLASK_SECRET_KEY` a été exposé :

1. **Régénérer immédiatement** un nouveau secret
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

2. **Mettre à jour .env**
```bash
FLASK_SECRET_KEY=NOUVEAU_SECRET_ICI
```

3. **Redémarrer l'application**
```bash
# Tous les clients seront déconnectés (normal)
python main_refactored.py
```

4. **Vérifier les logs** pour détecter des accès suspects

---

## 📞 Besoin d'aide ?

Pour des questions de sécurité :
- Consulter le [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md)
- Vérifier la documentation Flask-SocketIO : https://flask-socketio.readthedocs.io/

**Note** : Ce guide couvre les bases. Pour une production critique, considérez un audit de sécurité professionnel.
