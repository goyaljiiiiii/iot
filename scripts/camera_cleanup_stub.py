try:
    while True:
        # ... your existing camera code ...
finally:
    cap.release()
    cv2.destroyAllWindows()
    print("Camera released safely.")