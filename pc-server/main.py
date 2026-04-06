"""
VoiceMic PC Server - Entry Point
Usage: python main.py [--headless] [--port PORT]
"""
import sys
import argparse


def main():
    parser = argparse.ArgumentParser(description="VoiceMic PC Server")
    parser.add_argument("--headless", action="store_true", help="Run without GUI")
    parser.add_argument("--port", type=int, default=None, help="Server port")
    args = parser.parse_args()

    if args.headless:
        from server import AudioServer
        from audio_player import AudioPlayer
        from config import Config

        config = Config()
        port = args.port or config["port"]
        server = AudioServer(port=port)
        player = AudioPlayer(
            sample_rate=config["sample_rate"],
            channels=config["channels"],
            volume=config["volume"],
            device_name=config["output_device"],
        )

        def on_audio(data):
            player.feed(data)

        def on_connected(info):
            print(f"Connected: {info.device_name} @ {info.addr[0]}")
            player.sample_rate = info.sample_rate
            player.channels = info.channels
            player.start()

        def on_disconnected():
            print("Disconnected")
            player.stop()

        def on_status(msg):
            print(f"[STATUS] {msg}")

        def on_error(msg):
            print(f"[ERROR] {msg}")

        server.on_audio = on_audio
        server.on_client_connected = on_connected
        server.on_client_disconnected = on_disconnected
        server.on_status = on_status
        server.on_error = on_error

        server.start()
        ip = server.get_local_ip()
        print(f"VoiceMic Server (headless) running on {ip}:{port}")
        print("Press Ctrl+C to stop")

        try:
            import time
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down...")
            server.stop()
            player.stop()
    else:
        from gui import run
        run()


if __name__ == "__main__":
    main()
