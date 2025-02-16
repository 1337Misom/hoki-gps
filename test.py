import asyncio
import gi
import threading
from QGPS import QGPS

gi.require_version("Qrtr", "1.0")
gi.require_version("Qmi", "1.0")


from gi.repository import GLib


async def main():
    main_loop = GLib.MainLoop()
    loop_thread = threading.Thread(target=main_loop.run)
    loop_thread.start()

    gps = QGPS()

    await gps.open()

    await gps.register_events()
    await gps.set_nmea_types()
    await gps.start()
    await asyncio.sleep(100000)
    GLib.idle_add(main_loop.quit)


asyncio.run(main())
