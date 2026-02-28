# ChatCMS

ChatCMS is a lightweight content management system (CMS) built with Python.that innovatively uses the Deepseek API to automatically and periodically publish articles. It includes both public-facing templates and an admin panel, supporting articles, authors, categories, tags, file uploads, and basic search and pagination. The codebase is modular and easy to extend, making it a good starting point for small websites or blogs.

## Features
- Article, author, category and tag management
- Admin panel and public templates
- File uploads (article attachments, author avatars, etc.)
- Simple search and pagination
- Modular backend (models / services / crud) for easy extension

## Quick Start
1. Clone the repository and enter the project directory:

```bash
git clone https://github.com/tanzhimei393/chatcms.git
cd ChatCMS
```

2. Create and activate a virtual environment, then install dependencies:

```bash
python -m venv venv
venv\Scripts\activate    # Windows
pip install -r requirements.txt
```

3. Configuration (optional): edit `config.py` or add `google_service_account.json` if needed.

4. Run the application:

```bash
python main.py
```

5. Open your browser at `http://localhost:8000` (or the address printed by the app).

## Project Layout (brief)
- `main.py` — application entry point
- `config.py` — configuration
- `src/` — backend source code (`models.py`, `crud.py`, `services.py`, `controller.py`, `schemas.py`, etc.)
- `admin/`, `public/` — template directories
- `static/` — static assets
- `upload/` — uploaded files

## Contributing
Contributions are welcome. Please open issues or submit pull requests with concise change descriptions.

## License
This project defaults to the MIT License. If you prefer a different license, add a `LICENSE` file to the repository root.

---

## Deployment

Below are three common deployment options. Pick the one that matches your environment.

1) Docker (recommended for quick, reproducible deploys)

```Dockerfile
# Example Dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["python", "main.py"]
```

Build and run:

```bash
docker build -t chatcms:latest .
docker run -p 8000:8000 --env-file .env -v ./upload:/app/upload chatcms:latest
```

2) Gunicorn + Nginx (production-ready)

- Install Gunicorn and a WSGI entry if your app exposes one (for example `app = create_app()` in `main.py`).

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:8000 main:app
```

- Use Nginx as a reverse proxy to serve static files and forward requests to Gunicorn. Example Nginx server block:

```
server {
	listen 80;
	server_name example.com;

	location /static/ {
		alias /path/to/ChatCMS/static/;
	}

	location / {
		proxy_pass http://127.0.0.1:8000;
		proxy_set_header Host $host;
		proxy_set_header X-Real-IP $remote_addr;
		proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
	}
}
```

3) Heroku / PaaS (quick cloud deploy)

- Add a `Procfile`:

```
web: gunicorn main:app
```

- Ensure `requirements.txt` and `runtime.txt` (optional) are present, then `git push heroku main`.

Notes
- Environment configuration (database URL, secret keys, Google service account path) should be provided via environment variables or an `.env` file.
- Map the `upload/` folder to persistent storage (bind mount, cloud storage) in production.
- Tune Gunicorn worker count based on CPU and memory.

If you want, I can add a ready-to-use `Dockerfile`, `docker-compose.yml`, a `Procfile`, and an example Nginx config into the repo—tell me which files to generate.

## Support / Donate

If you'd like to support development, TRC20-USDT:


TKU9maWEjX34TGwCiPpDqmmty69ADxqAym


