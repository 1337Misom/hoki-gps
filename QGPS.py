from typing import Callable
import gi
import asyncio
import threading
import logging

gi.require_version("Qrtr", "1.0")
gi.require_version("Qmi", "1.0")

from gi.repository import GLib, Qrtr, Qmi, Gio

LOG = logging.getLogger("QGPS")
logging.basicConfig(level=logging.DEBUG)
LOG.setLevel(logging.DEBUG)


class QGPS:
    bus: Qrtr.Bus
    device: Qmi.Device
    client: Qmi.Client

    gps_port: int
    on_small_id: int
    on_large_id: int

    sensors: list["QGPS"]

    is_open: bool

    send_lock: asyncio.Lock

    def __init__(self):
        self.loop = asyncio.get_event_loop()
        self.is_open = False
        self.sensors = []
        self.send_lock = asyncio.Lock()

    async def _poll_event(self, event: threading.Event):
        while not event.is_set():
            await asyncio.sleep(0.2)

    def _run_once_glib(self, function: Callable, *args):
        try:
            function(*args)
        except Exception as ex:
            print(ex)
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
            | Qmi.LocEventRegistrationFlag.NI_NOTIFY_VERIFY_REQUEST
            | Qmi.LocEventRegistrationFlag.INJECT_TIME_REQUEST
            | Qmi.LocEventRegistrationFlag.INJECT_PREDICTED_ORBITS_REQUEST
            | Qmi.LocEventRegistrationFlag.INJECT_POSITION_REQUEST
            | Qmi.LocEventRegistrationFlag.ENGINE_STATE
            | Qmi.LocEventRegistrationFlag.FIX_SESSION_STATE
            | Qmi.LocEventRegistrationFlag.WIFI_REQUEST
            | Qmi.LocEventRegistrationFlag.SENSOR_STREAMING_READY_STATUS
            | Qmi.LocEventRegistrationFlag.TIME_SYNC_REQUEST
            | Qmi.LocEventRegistrationFlag.SET_SPI_STREAMING_REPORT
            | Qmi.LocEventRegistrationFlag.LOCATION_SERVER_CONNECTION_REQUEST
            | Qmi.LocEventRegistrationFlag.NI_GEOFENCE_NOTIFICATION
            | Qmi.LocEventRegistrationFlag.GEOFENCE_GENERAL_ALERT
            | Qmi.LocEventRegistrationFlag.GEOFENCE_BREACH_NOTIFICATION
            | Qmi.LocEventRegistrationFlag.PEDOMETER_CONTROL
            | Qmi.LocEventRegistrationFlag.MOTION_DATA_CONTROL
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
        for i in arr:
            # print("system:", i.system)
            # print("valid:", i.valid_information)
            # print("health:", i.health_status)
            # print("satellite:", i.satellite_status)
            pass

    def on_nmea_resp(self, client: Qmi.Client, nmea: Qmi.IndicationLocNmeaOutput):
        print(nmea.get_nmea_string(), end="")

    def qmi_allocate_client_callback(
        self, device: Qmi.Device, result: Gio.Task, user_data: threading.Event
    ):
        self.client = self.device.allocate_client_finish(result)
        LOG.debug("Adding callbacks")

        self.client.connect("nmea", self.on_nmea_resp)
        self.client.connect("gnss-sv-info", self.on_gnss_sv_info)

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

    async def start(self):
        inp = Qmi.MessageLocStartInput.new()
        inp.set_session_id(2)
        inp.set_intermediate_report_state(Qmi.LocIntermediateReportState.ENABLE)
        inp.set_minimum_interval_between_position_reports(10)
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

    def test_callback(self, name, *args):
        print(name, *args)

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
