import argparse
import glob
import sys
import time

import serial


def find_default_port():
    ports = sorted(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*"))
    return ports[0] if ports else None


def main():
    parser = argparse.ArgumentParser(description="Send test commands to Arduino over serial.")
    parser.add_argument("--port", default=None, help="Serial port (default: first /dev/ttyUSB* or /dev/ttyACM*)")
    parser.add_argument("--baud", type=int, default=9600, help="Baud rate (default: 9600)")
    parser.add_argument(
        "--sequence",
        default="G,1,2,3,P,0",
        help="Comma-separated commands to send (default: G,1,2,3,P,0)",
    )
    parser.add_argument("--delay", type=float, default=1.5, help="Delay between commands in seconds")
    parser.add_argument("--repeat", type=int, default=1, help="How many times to repeat the sequence")
    args = parser.parse_args()

    port = args.port or find_default_port()
    if not port:
        print("No serial port found. Plug in Arduino and try again.")
        sys.exit(1)

    commands = [cmd.strip() for cmd in args.sequence.split(",") if cmd.strip()]
    if not commands:
        print("Empty sequence.")
        sys.exit(1)

    print(f"Opening {port} @ {args.baud}")
    ser = serial.Serial(port, args.baud, timeout=0)
    time.sleep(2.0)  # allow board reset

    try:
        for n in range(args.repeat):
            print(f"Run {n + 1}/{args.repeat}")
            for cmd in commands:
                ser.write(cmd.encode("ascii", errors="ignore"))
                print(f"Sent: {cmd}")
                time.sleep(args.delay)
    finally:
        ser.close()
        print("Done.")


if __name__ == "__main__":
    main()
