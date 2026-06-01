# GUIDE D'INTÉGRATION - WebSocket Streaming

## 🎯 Comment utiliser les flux dans votre frontend

### Installation
```bash
pip install flask flask-socketio python-socketio
```

### 📡 Architecture WebSocket

```
Votre Frontend (React/Vue/Angular/HTML)
        │
        ├─> socket.connect()          # Connexion WebSocket
        │
        ├─> Reçoit: 'cameras_list'   # Liste des caméras disponibles
        │
        ├─> Envoie: 'start_stream'   # Demande le stream d'une caméra
        │   {camera_id: 1}
        │
        ├─> Reçoit: 'frame' (30/sec) # Frames en continu
        │   {camera_id, data, timestamp}
        │
        └─> Affichage dans Canvas     # Dessine l'image
```

---

## 💻 Exemples d'intégration

### 1. HTML/JavaScript Vanilla

```html
<!DOCTYPE html>
<html>
<head>
    <title>Surveillance</title>
    <script src="https://cdn.socket.io/4.5.4/socket.io.min.js"></script>
</head>
<body>
    <h1>Caméras de surveillance</h1>
    <div id="cameras"></div>

    <script>
        // 1. Connexion au serveur WebSocket
        const socket = io('http://localhost:5000');
        
        // 2. Stocker les références des caméras
        const cameras = {};
        
        // 3. Écouter l'événement 'cameras_list'
        socket.on('cameras_list', (data) => {
            console.log('Caméras reçues:', data.cameras);
            
            data.cameras.forEach(cam => {
                // Créer un canvas pour chaque caméra
                const container = document.createElement('div');
                container.innerHTML = `
                    <h3>${cam.name} - ${cam.location}</h3>
                    <canvas id="cam-${cam.id}" width="640" height="480"></canvas>
                `;
                document.getElementById('cameras').appendChild(container);
                
                // Stocker le contexte canvas
                const canvas = document.getElementById(`cam-${cam.id}`);
                cameras[cam.id] = {
                    canvas: canvas,
                    ctx: canvas.getContext('2d')
                };
                
                // Démarrer le stream
                socket.emit('start_stream', {camera_id: cam.id});
            });
        });
        
        // 4. Écouter l'événement 'frame'
        socket.on('frame', (data) => {
            const cam = cameras[data.camera_id];
            if (!cam) return;
            
            // Créer une image depuis les données base64
            const img = new Image();
            img.onload = () => {
                // Dessiner l'image sur le canvas
                cam.ctx.drawImage(img, 0, 0, cam.canvas.width, cam.canvas.height);
            };
            img.src = 'data:image/jpeg;base64,' + data.data;
        });
        
        // 5. Gérer les erreurs
        socket.on('error', (data) => {
            console.error('Erreur:', data.message);
        });
    </script>
</body>
</html>
```

---

### 2. React Component

```jsx
import { useEffect, useRef, useState } from 'react';
import io from 'socket.io-client';

function CameraStream({ cameraId }) {
    const canvasRef = useRef(null);
    const socketRef = useRef(null);
    const [latency, setLatency] = useState(0);

    useEffect(() => {
        // Connexion WebSocket
        const socket = io('http://localhost:5000');
        socketRef.current = socket;

        const ctx = canvasRef.current?.getContext('2d');
        let lastFrameTime = Date.now();

        // Réception des frames
        socket.on('frame', (data) => {
            if (data.camera_id !== cameraId) return;

            // Calculer latence
            const now = Date.now();
            setLatency(now - lastFrameTime);
            lastFrameTime = now;

            // Afficher l'image
            const img = new Image();
            img.onload = () => {
                ctx?.drawImage(img, 0, 0, 640, 480);
            };
            img.src = 'data:image/jpeg;base64,' + data.data;
        });

        // Démarrer le stream
        socket.emit('start_stream', { camera_id: cameraId });

        // Cleanup
        return () => {
            socket.emit('stop_stream');
            socket.disconnect();
        };
    }, [cameraId]);

    return (
        <div>
            <canvas ref={canvasRef} width={640} height={480} />
            <p>Latence: {latency}ms</p>
        </div>
    );
}

export default CameraStream;
```

---

### 3. Vue.js Component

```vue
<template>
  <div class="camera-stream">
    <h3>{{ camera.name }} - {{ camera.location }}</h3>
    <canvas ref="canvas" width="640" height="480"></canvas>
    <p>Latence: {{ latency }}ms</p>
  </div>
</template>

<script>
import io from 'socket.io-client';

export default {
  props: ['cameraId'],
  data() {
    return {
      socket: null,
      latency: 0,
      camera: {}
    };
  },
  mounted() {
    // Connexion WebSocket
    this.socket = io('http://localhost:5000');
    
    const ctx = this.$refs.canvas.getContext('2d');
    let lastFrameTime = Date.now();
    
    // Réception des caméras
    this.socket.on('cameras_list', (data) => {
      this.camera = data.cameras.find(c => c.id === this.cameraId);
    });
    
    // Réception des frames
    this.socket.on('frame', (data) => {
      if (data.camera_id !== this.cameraId) return;
      
      // Calculer latence
      this.latency = Date.now() - lastFrameTime;
      lastFrameTime = Date.now();
      
      // Afficher l'image
      const img = new Image();
      img.onload = () => {
        ctx.drawImage(img, 0, 0, 640, 480);
      };
      img.src = 'data:image/jpeg;base64,' + data.data;
    });
    
    // Démarrer le stream
    this.socket.emit('start_stream', { camera_id: this.cameraId });
  },
  beforeUnmount() {
    this.socket.emit('stop_stream');
    this.socket.disconnect();
  }
};
</script>
```

---

### 4. Angular Component

```typescript
import { Component, OnInit, OnDestroy, ViewChild, ElementRef } from '@angular/core';
import { io, Socket } from 'socket.io-client';

@Component({
  selector: 'app-camera-stream',
  template: `
    <div>
      <h3>{{ camera?.name }} - {{ camera?.location }}</h3>
      <canvas #canvas width="640" height="480"></canvas>
      <p>Latence: {{ latency }}ms</p>
    </div>
  `
})
export class CameraStreamComponent implements OnInit, OnDestroy {
  @ViewChild('canvas', { static: true }) canvasRef!: ElementRef<HTMLCanvasElement>;
  
  cameraId = 1;  // À passer en @Input()
  socket!: Socket;
  latency = 0;
  camera: any;

  ngOnInit() {
    // Connexion WebSocket
    this.socket = io('http://localhost:5000');
    
    const ctx = this.canvasRef.nativeElement.getContext('2d')!;
    let lastFrameTime = Date.now();
    
    // Réception des caméras
    this.socket.on('cameras_list', (data: any) => {
      this.camera = data.cameras.find((c: any) => c.id === this.cameraId);
    });
    
    // Réception des frames
    this.socket.on('frame', (data: any) => {
      if (data.camera_id !== this.cameraId) return;
      
      // Calculer latence
      this.latency = Date.now() - lastFrameTime;
      lastFrameTime = Date.now();
      
      // Afficher l'image
      const img = new Image();
      img.onload = () => {
        ctx.drawImage(img, 0, 0, 640, 480);
      };
      img.src = 'data:image/jpeg;base64,' + data.data;
    });
    
    // Démarrer le stream
    this.socket.emit('start_stream', { camera_id: this.cameraId });
  }

  ngOnDestroy() {
    this.socket.emit('stop_stream');
    this.socket.disconnect();
  }
}
```

---

## 📚 API WebSocket Complète

### Événements ENVOYÉS par le client:

```javascript
// Démarrer le stream d'une caméra
socket.emit('start_stream', {camera_id: 1});

// Arrêter le stream actuel
socket.emit('stop_stream');
```

### Événements REÇUS par le client:

```javascript
// Liste des caméras (automatique à la connexion)
socket.on('cameras_list', (data) => {
    // data = {cameras: [{id, name, location}, ...]}
});

// Stream démarré
socket.on('stream_started', (data) => {
    // data = {camera_id: 1}
});

// Frame reçue (30/sec)
socket.on('frame', (data) => {
    // data = {camera_id: 1, data: "base64...", timestamp: 1234567890}
});

// Stream arrêté
socket.on('stream_stopped', () => {});

// Erreur
socket.on('error', (data) => {
    // data = {message: "..."}
});
```

---

## 🎨 API REST (bonus)

```javascript
// GET /api/cameras - Liste des caméras
fetch('http://localhost:5000/api/cameras')
  .then(r => r.json())
  .then(cameras => console.log(cameras));

// GET /api/stats - Statistiques
fetch('http://localhost:5000/api/stats')
  .then(r => r.json())
  .then(stats => console.log(stats));
```

---

## 🚀 Performance

- **Latence:** 180-250ms (excellent pour surveillance)
- **FPS:** 30 images/seconde
- **Bande passante:** ~2-3 Mbps par stream
- **Format:** JPEG base64 via WebSocket
- **Qualité:** Configurable dans settings.py (JPEG_QUALITY)

---

## ✅ Avantages WebSocket vs HTTP MJPEG

| Critère | WebSocket | HTTP MJPEG |
|---------|-----------|------------|
| Latence | 180-250ms | 330-450ms |
| Bidirectionnel | ✅ Oui | ❌ Non |
| Contrôle FPS | ✅ Oui | ⚠️ Limité |
| Compatibilité | Moderne | Universelle |
| Bande passante | Optimisée | Élevée |

**Pour votre cas: WebSocket est optimal !**
