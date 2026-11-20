#!/usr/bin/env python3
# 英文課筆記本：本機 Gemini API 中介伺服器
# API Key 只在啟動時輸入，隱藏輸入，不會寫進 HTML 或這個檔案。

import json
import os
import getpass
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

HOST = "127.0.0.1"
PORT = 8000
MODEL = "gemini-3.8-flash"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"

API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    API_KEY = getpass.getpass("請貼上 Gemini API Key（輸入時不會顯示）：").strip()

if not API_KEY:
    raise SystemExit("沒有輸入 API Key，伺服器已停止。")

class Handler(SimpleHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/api/gem":
            self.send_json(404, {"error": "找不到這個 API 路徑"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 2_000_000:
                self.send_json(413, {"error": "請求內容為空或超過 2 MB"})
                return

            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            contents = payload.get("contents", [])
            system = payload.get("system", "")

            if not isinstance(contents, list) or not contents:
                self.send_json(400, {"error": "沒有收到要送給 Gemini 的內容"})
                return

            gemini_contents = []
            for item in contents:
                if not isinstance(item, dict):
                    continue
                role = item.get("role", "user")
                role = "model" if role in ("model", "assistant") else "user"
                parts = item.get("parts", [])
                text_parts = []
                for part in parts:
                    if isinstance(part, dict) and isinstance(part.get("text"), str):
                        text_parts.append({"text": part["text"]})
                if text_parts:
                    gemini_contents.append({"role": role, "parts": text_parts})

            while gemini_contents and gemini_contents[0]["role"] != "user":
                gemini_contents.pop(0)

            if not gemini_contents:
                self.send_json(400, {"error": "沒有可用的文字內容"})
                return

            request_body = {"contents": gemini_contents}
            if isinstance(system, str) and system.strip():
                request_body["systemInstruction"] = {
                    "parts": [{"text": system}]
                }

            req = urllib.request.Request(
                GEMINI_URL,
                data=json.dumps(request_body).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": API_KEY,
                },
                method="POST",
            )

            try:
                with urllib.request.urlopen(req, timeout=90) as response:
                    result = json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", errors="replace")
                try:
                    parsed = json.loads(detail)
                    message = parsed.get("error", {}).get("message", detail)
                except Exception:
                    message = detail
                self.send_json(e.code, {"error": f"Gemini 回應錯誤：{message}"})
                return
            except Exception as e:
                self.send_json(502, {"error": f"連線 Gemini 失敗：{e}"})
                return

            candidates = result.get("candidates", [])
            answer_parts = (
                candidates[0].get("content", {}).get("parts", [])
                if candidates else []
            )
            answer = "".join(
                p.get("text", "") for p in answer_parts
                if isinstance(p, dict) and isinstance(p.get("text"), str)
            )

            if not answer:
                self.send_json(502, {"error": "Gemini 沒有產生文字，請檢查內容或模型回應"})
                return

            self.send_json(200, {"text": answer})

        except json.JSONDecodeError:
            self.send_json(400, {"error": "收到的資料不是有效 JSON"})
        except Exception as e:
            self.send_json(500, {"error": f"本機伺服器錯誤：{e}"})

    def send_json(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # 不記錄請求本文或 API Key
        print("%s - %s" % (self.address_string(), format % args))

if __name__ == "__main__":
    os.chdir(Path(__file__).resolve().parent)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"英文課筆記本已啟動：http://{HOST}:{PORT}/英文課筆記本_Gemini版.html")
    print("請保持這個終端機視窗開啟；按 Ctrl + C 可停止。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\\n伺服器已停止。")
    finally:
        server.server_close()
