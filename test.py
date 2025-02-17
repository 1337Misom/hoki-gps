import asyncio
import gi
import threading
import argparse
import logging
from QGPS import QGPS

gi.require_version("Qrtr", "1.0")
gi.require_version("Qmi", "1.0")


from gi.repository import GLib, Qmi

LOG_FORMAT = "[%(name)s][%(levelname)s]: %(message)s"
LOG_MAP = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


async def on_nmea(nmea: str):
    print(f"{nmea[:-1]}")


async def get_satellite_count(
    satellites: list[Qmi.IndicationLocGnssSvInfoOutputListElement],
):
    idle = len(
        [i for i in satellites if i.satellite_status == Qmi.LocSatelliteStatus.IDLE]
    )
    searching = len(
        [
            i
            for i in satellites
            if i.satellite_status == Qmi.LocSatelliteStatus.SEARCHING
        ]
    )
    tracking = len(
        [i for i in satellites if i.satellite_status == Qmi.LocSatelliteStatus.TRACKING]
    )

    return (idle, searching, tracking)


async def on_satellite_info(info: list[Qmi.IndicationLocGnssSvInfoOutputListElement]):
    gps_satellites = [i for i in info if i.system == Qmi.LocSystem.GPS]
    galileo_satellites = [i for i in info if i.system == Qmi.LocSystem.GALILEO]
    sbas_satellites = [i for i in info if i.system == Qmi.LocSystem.SBAS]
    beidou_satellites = [i for i in info if i.system == Qmi.LocSystem.COMPASS]
    glonass_satellites = [i for i in info if i.system == Qmi.LocSystem.GLONASS]

    gps_satellites_cnt = await get_satellite_count(gps_satellites)
    galileo_satellites_cnt = await get_satellite_count(galileo_satellites)
    sbas_satellites_cnt = await get_satellite_count(sbas_satellites)
    beidou_satellites_cnt = await get_satellite_count(beidou_satellites)
    glonass_satellites_cnt = await get_satellite_count(glonass_satellites)
    print("Satellite Info (idle/searching/tracking):")
    print(
        f"    GPS     :({gps_satellites_cnt[0]}/{gps_satellites_cnt[1]}/{gps_satellites_cnt[2]})"
    )
    print(
        f"    Galileo :({galileo_satellites_cnt[0]}/{galileo_satellites_cnt[1]}/{galileo_satellites_cnt[2]})"
    )
    print(
        f"    SBAS    :({sbas_satellites_cnt[0]}/{sbas_satellites_cnt[1]}/{sbas_satellites_cnt[2]})"
    )
    print(
        f"    BeiDou  :({beidou_satellites_cnt[0]}/{beidou_satellites_cnt[1]}/{beidou_satellites_cnt[2]})"
    )
    print(
        f"    GLONASS :({glonass_satellites_cnt[0]}/{glonass_satellites_cnt[1]}/{glonass_satellites_cnt[2]})"
    )


async def main():
    parser = argparse.ArgumentParser(
        description="A simple script to log the location received through libqmi"
    )
    parser.add_argument(
        "-n", "--nmea", action="store_true", help="print nmea to terminal"
    )

    parser.add_argument(
        "-i", "--info", action="store_true", help="print satellite info to terminal"
    )
    parser.add_argument(
        "-d", "--duration", help="set duration to run", type=int, default=1000
    )

    parser.add_argument(
        "--log_level",
        default="INFO",
        help="Log level to use",
        required=False,
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    )

    args = parser.parse_args()

    log_level = LOG_MAP[args.log_level]
    logging.basicConfig(level=log_level, format=LOG_FORMAT, force=True)

    main_loop = GLib.MainLoop()
    loop_thread = threading.Thread(target=main_loop.run)
    loop_thread.start()

    gps = QGPS(on_nmea if args.nmea else None, on_satellite_info if args.info else None)

    await gps.open()

    await gps.register_events()
    await gps.set_nmea_types()
    await gps.start()
    await asyncio.sleep(args.duration)
    GLib.idle_add(main_loop.quit)


asyncio.run(main())
