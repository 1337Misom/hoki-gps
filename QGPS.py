from typing import Callable
import gi
import asyncio
import threading
import logging

gi.require_version("Qrtr", "1.0")
gi.require_version("Qmi", "1.0")

from gi.repository import GLib, Qrtr, Qmi, Gio

LOG = logging.getLogger("QGPS")


class QGPS:
    bus: Qrtr.Bus
    device: Qmi.Device
    client: Qmi.Client

    on_nmea_callback: Callable | None
    on_satellite_info_callback: Callable | None

    gps_port: int

    is_open: bool

    def __init__(
        self, on_nmea: Callable | None = None, on_satellite_info: Callable | None = None
    ):
        self.loop = asyncio.get_event_loop()
        self.is_open = False
        self.sensors = []
        self.send_lock = asyncio.Lock()
        self.on_nmea_callback = on_nmea
        self.on_satellite_info_callback = on_satellite_info

    async def _poll_event(self, event: threading.Event):
        while not event.is_set():
            await asyncio.sleep(0.2)

    def _run_once_glib(self, function: Callable, *args):
        function(*args)
        return False

    def engine_loc_ready(
        self, client: Qmi.Client, result: Gio.Task, event: threading.Event
    ):
        out = self.client.set_engine_lock_finish(result)
        out.get_result()
        event.set()

    def set_op_mode_ready(
        self, client: Qmi.Client, result: Gio.Task, event: threading.Event
    ):
        out = self.client.set_operation_mode_finish(result)
        out.get_result()
        event.set()

    def set_registers_ready(
        self, client: Qmi.Client, result: Gio.Task, event: threading.Event
    ):
        out = self.client.set_operation_mode_finish(result)
        out.get_result()
        event.set()

    async def register_events(self):
        event = threading.Event()
        inp = Qmi.MessageLocRegisterEventsInput.new()
        inp.set_event_registration_mask(
            Qmi.LocEventRegistrationFlag.POSITION_REPORT
            | Qmi.LocEventRegistrationFlag.GNSS_SATELLITE_INFO
            | Qmi.LocEventRegistrationFlag.NMEA
        )

        GLib.idle_add(
            self._run_once_glib,
            self.client.register_events,
            inp,
            10,
            None,
            self.set_registers_ready,
            event,
        )
        await self._poll_event(event)

    async def set_op_mode(self):
        event = threading.Event()
        inp = Qmi.MessageLocSetOperationModeInput.new()
        inp.set_operation_mode(Qmi.LocOperationMode.STANDALONE)
        GLib.idle_add(
            self._run_once_glib,
            self.client.set_operation_mode,
            inp,
            10,
            None,
            self.set_op_mode_ready,
            event,
        )
        await self._poll_event(event)

    async def set_engine_lock(self):
        event = threading.Event()
        inp = Qmi.MessageLocSetEngineLockInput.new()
        inp.set_lock_type(Qmi.LocLockType.NONE)
        GLib.idle_add(
            self._run_once_glib,
            self.client.set_engine_lock,
            inp,
            10,
            None,
            self.engine_loc_ready,
            event,
        )
        await self._poll_event(event)

    async def open(self):
        LOG.debug("Opening GPS")
        event = threading.Event()
        GLib.idle_add(
            self._run_once_glib,
            Qrtr.Bus.new,
            1000,
            None,
            self.qrtr_new_bus_callback,
            event,
        )
        await self._poll_event(event)
        self.is_open = True
        LOG.debug("GPS opened")

    def on_gnss_sv_info(
        self, client: Qmi.Client, sv_info: Qmi.IndicationLocGnssSvInfoOutput
    ):
        arr = sv_info.get_list()
        if self.on_satellite_info_callback:
            asyncio.run_coroutine_threadsafe(
                self.on_satellite_info_callback(arr),
                self.loop,
            )

    def on_nmea_resp(self, client: Qmi.Client, nmea: Qmi.IndicationLocNmeaOutput):
        if self.on_nmea_callback:
            asyncio.run_coroutine_threadsafe(
                self.on_nmea_callback(nmea.get_nmea_string()),
                self.loop,
            )
        else:
            LOG.debug(f"NMEA: {nmea.get_nmea_string()[:-1]}")  # discard newline

    def on_position_report(
        self, client: Qmi.Client, report: Qmi.IndicationLocPositionReportOutput
    ):
        try:
            vertical_reliability = report.get_vertical_uncertainty()
            horizontal_reliability = report.get_horizontal_uncertainty_circular()
            sats_used = report.get_satellites_used()
            LOG.debug(
                f"Horizontal/Vertical accuracy (sats: {len(sats_used)}): {horizontal_reliability}m/{vertical_reliability}m"
            )

            lat = report.get_latitude()
            lon = report.get_longitude()
            altitude = report.get_altitude_from_sealevel()
            LOG.debug(f"Lat/Lon/altitude: {lat}/{lon}/{altitude:.2f}m")
        except:
            # Happens when there is no position available
            pass

    def qmi_allocate_client_callback(
        self, device: Qmi.Device, result: Gio.Task, user_data: threading.Event
    ):
        self.client = self.device.allocate_client_finish(result)
        LOG.debug("Adding callbacks")

        self.client.connect("nmea", self.on_nmea_resp)
        self.client.connect("gnss-sv-info", self.on_gnss_sv_info)
        self.client.connect("position-report", self.on_position_report)

        user_data.set()

    def set_nmea_types_ready(
        self, client: Qmi.Client, result: Gio.Task, event: threading.Event
    ):
        out = self.client.set_nmea_types_finish(result)
        out.get_result()
        event.set()

    async def set_nmea_types(self):
        event = threading.Event()
        inp = Qmi.MessageLocSetNmeaTypesInput.new()
        inp.set_nmea_types(
            Qmi.LocNmeaType.GSA
            | Qmi.LocNmeaType.GSV
            | Qmi.LocNmeaType.VTG
            | Qmi.LocNmeaType.RMC
            | Qmi.LocNmeaType.GGA
            | Qmi.LocNmeaType.PSTIS
        )
        GLib.idle_add(
            self._run_once_glib,
            self.client.set_nmea_types,
            inp,
            10,
            None,
            self.set_nmea_types_ready,
            event,
        )
        await self._poll_event(event)

    async def start(self, time_between_positions: int = 500):
        inp = Qmi.MessageLocStartInput.new()
        inp.set_session_id(2)
        inp.set_intermediate_report_state(Qmi.LocIntermediateReportState.ENABLE)
        inp.set_minimum_interval_between_position_reports(time_between_positions)
        inp.set_fix_recurrence_type(Qmi.LocFixRecurrenceType.PERIODIC_FIXES)
        event = threading.Event()
        GLib.idle_add(
            self._run_once_glib,
            self.client.start,
            inp,
            10,
            None,
            self.start_ready,
            event,
        )
        await self._poll_event(event)
        LOG.debug("Started Location")

    def start_ready(self, client: Qmi.Client, result: Gio.Task, event: threading.Event):
        out = self.client.start_finish(result)
        if not out:
            LOG.error("Couldn't start")
            raise RuntimeError("Error while starting location")
        out.get_result()
        event.set()

    def qmi_open_device_callback(
        self, device: Qmi.Device, result: Gio.Task, user_data: threading.Event
    ):
        self.device.open_finish(result)
        LOG.debug("Allocating Client")
        self.device.allocate_client(
            Qmi.Service.LOC,
            Qmi.CID_NONE,
            self.gps_port,
            None,
            self.qmi_allocate_client_callback,
            user_data,
        )

    def qmi_new_device_callback(
        self, device: Qmi.Device, result: Gio.Task, user_data: threading.Event
    ):
        self.device = Qmi.Device.new_finish(result)
        LOG.debug("Opening Device")
        Qmi.Device.open(
            self.device,
            Qmi.DeviceOpenFlags.AUTO | Qmi.DeviceOpenFlags.EXPECT_INDICATIONS,
            self.gps_port,
            None,
            self.qmi_open_device_callback,
            user_data,
        )

    def qrtr_new_bus_callback(
        self, bus: Qrtr.Bus, result: Gio.Task, user_data: threading.Event
    ):
        LOG.debug("New bus")
        self.bus = Qrtr.Bus.new_finish(result)

        found = None
        gps_port = 0
        for node in self.bus.peek_nodes():
            if (gps_port := node.lookup_port(Qmi.Service.LOC)) >= 0:
                found = node
                self.gps_port = gps_port
                break
        if not found:
            LOG.error("No gps service found")
            raise RuntimeError("Unable to find GPS Service")
        LOG.debug("Creating Device")
        Qmi.Device.new_from_node(found, None, self.qmi_new_device_callback, user_data)
