# EduVerse 3D — Adaptive Learning Lab Prototype

A browser-based concept prototype for the EduVerse 3D idea. The dashboard frames an adaptive learning experience around an interactive binary-search challenge, with evidence-based concept estimates and targeted retry feedback.

## Run it

Open `index.html` directly in a browser. This prototype uses plain HTML, CSS, and JavaScript and does not require a build step or server.

## Prototype interactions

- **Resume lab** opens a binary-search decision challenge.
- Choose an answer to see targeted feedback. Complete the challenge to update the Search boundaries estimate in the Learning Twin.
- **Try it** opens the same challenge.
- **Ask learning guide** opens a small Nova explainer for the midpoint decision.

## Scope

The Learning Twin values are illustrative client-side prototype state. There is no account system, backend persistence, generative AI, or real 3D scene yet. The visual lab card communicates the immersive direction; the challenge demonstrates the learning loop that should drive the product.

## Suggested next build

Connect learning events and assessment attempts to a backend, represent concepts and prerequisites explicitly, then build the first Three.js lab around binary search. Keep observed events distinct from mastery estimates and show the evidence behind recommendations.

## Screen navigation

Use the sidebar to move between the dashboard, course catalog, lesson player, 3D campus, virtual classroom, library, and profile/progress screens. The profile avatar opens the onboarding role-selection preview. Campus buildings open their associated areas; the campus map toggle switches to a flatter, low-performance view.

These are front-end screen prototypes with demo content. Authentication, live classes, persistence, accessibility preference storage, and 3D networking are not connected yet.

## Start the API

Requires Node.js 18 or newer; no third-party packages are needed.

```bash
cd eduverse-3d/backend
npm start
```

The API listens at `http://localhost:4173`. Keep it running, then open `eduverse-3d/index.html` in a browser. The prototype reads the course catalog and profile/progress from the API, and posts binary-search attempts. Data is stored in `backend/data/store.json`.

### API routes

- `GET /api/health`
- `GET /api/courses?q=&level=`
- `GET` and `PATCH /api/profile`
- `GET /api/progress`
- `POST /api/attempts` with `{ "activityId": "binary-search-boundary", "answer": "left" | "right" }`

This is a local demo API with a single seeded learner. It does not provide authentication or multi-user isolation; do not expose it to the public internet as-is.

## Student and teacher experiences

- **3D Campus:** draggable, orbiting WebGL campus with portals into courses, the lab, and classroom; the 2D map toggle is available for simpler devices.
- **Virtual classroom:** editable shared-board preview, pen/erase controls, sticky notes, quick poll, raise hand, and participant/chat panel. Saving the board adds it to Notes.
- **Notes Studio:** edit and save notes through `POST /api/notes`; the API stores them in the local JSON store. A browser-local fallback is used if the API is offline.
- **Coding paths:** API-backed module outlines for web development, DSA, and backend engineering, with capstone project ideas.
- **Teacher Studio:** lesson planning, class board, and learner-progress entry points. The top-right role switch persists the demo role to the profile endpoint.

The classroom and teacher tools are single-browser demos. Live multi-user board synchronization, real-time calls, course authoring workflows, account security, and production 3D assets would need additional services and implementation.

### Recent improvements

Learning Twin and Community now have working navigation destinations. The lesson player includes recently watched and suggested activities. Assignments support teacher creation and student text submissions. Profile settings can change the saved daily goal and theme. Course cards and coding-language cards use photographic thumbnails. The language library includes 20 widely used languages and web technologies across web, general-purpose, systems, and data categories.

### Teacher, library, and support tools

- Teacher Studio stores class schedules, attendance, practice questions, and tests through `/api/teacher` routes. Learners can submit answers to published tests for teacher review.
- The classroom board saves locally first, restores notes on return, and syncs board notes into the Notes area when the API is running.
- Profile details are demo fields: ID and join date are clearly labelled demo values; age and institution are optional and can be edited in the profile.
- Notifications can be marked read; resource cards open full reading context and can be added to a browser-local reading list.
- Feedback is stored by the local API, with a browser-local fallback. Nova is a scripted prototype assistant, not a live AI connection.
- Sidebar navigation scrolls on smaller screens. Playlist links will appear in the library when supplied.

## Computer Vision Labs

The **Vision & Simulation Lab** opens 19 activities, grouped into computer vision, virtual science, and applied learning. It includes webcam drawing, air keyboard, gesture presentation and training, chemistry, projectile physics, cell biology, circuits, gear ratios, object color hunt, board cleanup, accessibility dwell selection, body framing, 3D molecule interaction, a movement game, coding controls, avatar motion, face/environment interaction, and Teach EduVerse. Simulations include objectives, live controls, quick checks, and saved progress where applicable.

The gesture lab trains an in-memory nearest-neighbour baseline on the learner's labeled contour samples. It is an educational demo, not a production gesture model. The scavenger hunt estimates center-frame color and does not identify object names. The scanner uses OpenCV to enhance contrast locally; it does not perform OCR, so learners type the equation for the step explainer. Eye direction is a rough experimental estimate; body framing uses OpenCV's built-in HOG detector and does not estimate posture. The face/environment activity does not infer emotion or identity. Science and physics activities are simplified educational models.

## Webcam Drawing Studio (OpenCV + Python)

1. Start the OpenCV tracker in a separate terminal (macOS/Linux):

   ```bash
   cd "eduverse-3d/opencv-drawing"
   python3 -m venv .venv
   .venv/bin/python -m pip install -r requirements.txt
   .venv/bin/python server.py
   ```

   OpenCV 4 is pinned because the tracker uses its Haar cascade and HOG detectors. On Windows, use `.venv\Scripts\python.exe` in place of `.venv/bin/python`.

2. Open EduVerse, choose **Webcam drawing**, and press **Start camera**. Allow webcam access in the browser when prompted. Raise a finger in view to guide the brush. Use Pause, Clear, and Save image for the canvas.

The browser streams reduced camera frames only to the local OpenCV service at `127.0.0.1:4174`; frames are processed in memory and are not stored. The **Hand drawing** mode uses local contour tracking. **Live Sketch · Canny 10/80** and **Live Sketch · Canny 30/60** apply the two supplied webcam sketch pipelines frame by frame; these transform video into edge art and do not track a hand. Pause, clear, mouse drawing, brush color/size, eraser, save image, and the triangle challenge are available. The shared tracker also drives air-key dwell typing, presentation controls, and other camera experiments. The whiteboard scanner enhances images locally; equation OCR is not included. Webcam access is requested only after Start. Lighting and background can affect contour tracking accuracy.

The two sketch filter recipes were adapted from the user-provided `livecam-sketching` example by Yashwant (2019) and `Live-Video-Sketching-through-webcam-using-OpenCv-Python` by Kaushik Jadhav. The first archive's MIT notice is preserved in [`LICENSES/livecam-sketching-MIT.txt`](LICENSES/livecam-sketching-MIT.txt). The second archive did not include a license file; only its described Canny settings were used as a reference. The notebook dependencies such as Keras are not needed for these filters.
