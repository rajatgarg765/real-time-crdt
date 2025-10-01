master branch
 uvicorn main:app --reload --host 0.0.0.0 --port 8000
 python -m http.server 8001


http://localhost:8001/index.html?doc=doc1&user=alice
http://localhost:8001/index.html?doc=doc1&user=bob
