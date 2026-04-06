"""
VoiceMic PC Client - Entry Point
Usage: python main.py [--headless --ip IP] [--port PORT]
"""
import sys
import argparse


def main():
    parser = argparse.ArgumentParser(description="VoiceMic PC Client")
    parser.add_argument("--headless", action="store_true", help="Run without GUI")
    parser.add_argument("--ip", type=str, default=None, help="Phone IP address (required for headless)")
    parser.add_argument("--port", type=int, default=None, help="Control port")
    args = parser.parse_args()

    if args.headless:
        if not args.ip:
            parser.error("--ip is required in headless mode")

        from server import AudioClient
        from audio_player import AudioPlayer
        from config import Config

        config = Config()
        port = args.port or config["control_port"]
        client = AudioClient(port=port)
        player = AudioPlayer(
            sample_rate=config["sample_rate"],
            channels=config["channels"],
            volume=config["volume"],
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

        client.on_audio = on_audio
        client.on_client_connected = on_connected
        client.on_client_disconnected = on_disconnected
        client.on_status = on_status
        client.on_error = on_error

        client.connect(args.ip, port)
        print(f"VoiceMic Client (headless) connecting to {args.ip}:{port}")
        print("Press Ctrl+C to stop")

        try:
            import time
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down...")
            client.stop()
            player.stop()
    else:
        from gui import run
        run()


if __name__ == "__main__":
    main()
