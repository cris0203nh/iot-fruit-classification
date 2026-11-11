import json
import threading
from datetime import datetime, timezone

import serial
import httpx

PORT = "COM3"
BAUDRATE = 115200
API_URL = "http://127.0.0.1:8000/api/iot/measurements"

write_lock = threading.Lock()
running = True


def send_command(ser):
    global running

    print("\nComandos disponibles: TARE, CAL 500, SAVE, STATUS")
    print("Escribe un comando y presiona Enter.\n")

    while running:
        try:
            command = input("ESP32> ").strip()

            if not command:
                continue

            command = command.strip().upper()

            if command not in ("TARE", "SAVE", "STATUS") and not command.startswith("CAL "):
                print("Comando no reconocido.")
                continue

            with write_lock:
                ser.write((command + "\n").encode("utf-8"))
                ser.flush()

            print(f"Comando enviado: {command}")

        except (EOFError, KeyboardInterrupt):
            break
        except Exception as exc:
            print(f"Error enviando comando: {exc}")
            break


def main():
    global running

    print("================================")
    print(" AGROSCAN - PUENTE SERIAL ESP32")
    print("================================")

    with serial.Serial(PORT, BAUDRATE, timeout=1) as ser:
        print(f"Puerto conectado: {PORT}")
        print(f"Velocidad: {BAUDRATE}")
        print("Esperando reinicio y telemetría del ESP32...")

        with httpx.Client(timeout=5.0) as client:
            input_thread = threading.Thread(
                target=send_command,
                args=(ser,),
                daemon=True
            )
            input_thread.start()

            try:
                while True:
                    raw = ser.readline()

                    if not raw:
                        continue

                    line = raw.decode("utf-8", errors="replace").strip()

                    if not line.startswith("{"):
                        print(f"[SERIAL] {line}")
                        continue

                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        print("[JSON] Mensaje inválido")
                        continue

                    if data.get("type") == "event":
                        print(f"[ESP32] {data}")
                        continue

                    if data.get("type") != "telemetry":
                        continue

                    print(
                        f"[BALANZA] Estado: {data.get('status')} | "
                        f"RAW: {data.get('raw_mean')}"
                    )

                    measurement = data.get("measurement")

                    if not isinstance(measurement, dict):
                        continue

                    # El firmware no envía observed_at.
                    # El backend exige este campo.
                    payload = dict(measurement)
                    payload["observed_at"] = (
                        datetime.now(timezone.utc).isoformat()
                    )

                    try:
                        response = client.post(API_URL, json=payload)
                        response.raise_for_status()

                        result = response.json()

                        print(
                            f"[API OK] Peso: {payload['weight_g']} g | "
                            f"Estable: {payload['stable']} | "
                            f"Duplicado: {result.get('duplicate')}"
                        )

                    except httpx.HTTPStatusError as exc:
                        print(
                            f"[API ERROR] HTTP {exc.response.status_code}: "
                            f"{exc.response.text}"
                        )

                    except httpx.RequestError as exc:
                        print(f"[API ERROR] No se pudo contactar FastAPI: {exc}")

            except KeyboardInterrupt:
                print("\nCerrando puente serial...")

            finally:
                running = False

    print("Puente serial cerrado.")


if __name__ == "__main__":
    main()
