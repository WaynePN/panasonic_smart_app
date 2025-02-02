import logging
from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import (
    UnitOfTemperature,
    ATTR_TEMPERATURE,
)

from .entity import PanasonicBaseEntity
from .const import (
    DOMAIN,
    DEVICE_TYPE_AC,
    DEVICE_TYPE_ERV,
    DATA_CLIENT,
    DATA_COORDINATOR,
    CLIMATE_AVAILABLE_MODE,
    CLIMATE_AVAILABLE_PRESET,
    CLIMATE_AVAILABLE_SWING_MODE,
    CLIMATE_AVAILABLE_FAN_MODE,
    CLIMATE_TEMPERATURE_STEP,
    LABEL_CLIMATE,
    LABEL_ERV,
)

_LOGGER = logging.getLogger(__package__)


def getKeyFromDict(targetDict, mode_name):
    for key, value in targetDict.items():
        if mode_name == value:
            return key

    return None


async def async_setup_entry(hass, entry, async_add_entities) -> bool:
    client = hass.data[DOMAIN][entry.entry_id][DATA_CLIENT]
    coordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    devices = coordinator.data
    climate = []

    for index, device in enumerate(devices):
        if int(device.get("DeviceType")) == DEVICE_TYPE_AC:
            climate.append(
                PanasonicClimate(
                    coordinator,
                    index,
                    client,
                    device,
                )
            )

        if int(device.get("DeviceType")) == DEVICE_TYPE_ERV:
            climate.append(
                PanasonicERV(
                    coordinator,
                    index,
                    client,
                    device,
                )
            )

    async_add_entities(climate, True)

    return True


class PanasonicClimate(PanasonicBaseEntity, ClimateEntity):
    @property
    def available(self) -> bool:
        status = self.coordinator.data[self.index]["status"]
        return status.get("0x00", None) != None

    @property
    def label(self) -> str:
        return f"{self.nickname} {LABEL_CLIMATE}"

    @property
    def supported_features(self) -> int:
        """Return the list of supported features."""
        status = self.coordinator.data[self.index]["status"]
        features = (
            ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
            | ClimateEntityFeature.TARGET_TEMPERATURE
        )

        _raw_swing_mode = int(status.get("0x0F", 0))
        _swing_mode = _raw_swing_mode in CLIMATE_AVAILABLE_SWING_MODE
        
        _raw_fan_mode = int(status.get("0x02", 0))
        _fan_mode = _raw_fan_mode in CLIMATE_AVAILABLE_FAN_MODE

        if _swing_mode:
            features |= ClimateEntityFeature.SWING_MODE
        if _fan_mode:
            features |= ClimateEntityFeature.FAN_MODE

        return features

    @property
    def temperature_unit(self) -> str:
        return UnitOfTemperature.CELSIUS

    @property
    def hvac_mode(self) -> str:
        status = self.coordinator.data[self.index]["status"]
        _is_on = bool(int(status.get("0x00", 0)))

        if not _is_on:
            _LOGGER.debug(f"[{self.label}] hvac_mode: off")
            return HVACMode.OFF
        else:
            if not status.get("0x01", None):
                return ""

            value = int(status.get("0x01"))
            mode_mapping = list(
                filter(lambda m: m["mappingCode"] == value, CLIMATE_AVAILABLE_MODE)
            )[0]
            _LOGGER.debug(f"[{self.label}] hvac_mode: {mode_mapping['key']}")
            return mode_mapping["key"]

    @property
    def hvac_modes(self) -> list:
        raw_modes = list(filter(lambda c: c["CommandType"] == "0x01", self.commands))[
            0
        ]["Parameters"]

        def mode_extractor(mode):
            mode_mapping = list(
                filter(lambda m: m["mappingCode"] == mode[1], CLIMATE_AVAILABLE_MODE)
            )[0]
            return mode_mapping["key"]

        _hvac_modes = list(map(mode_extractor, raw_modes))

        """ Force adding off mode into list """
        _hvac_modes.append(HVACMode.OFF)

        _LOGGER.debug(f"[{self.label}] hvac_modes: {_hvac_modes}")

        return _hvac_modes

    async def async_set_hvac_mode(self, hvac_mode) -> None:
        status = self.coordinator.data[self.index]["status"]
        _is_on = bool(int(status.get("0x00", 0)))

        _LOGGER.debug(f"[{self.label}] set_hvac_mode: {hvac_mode}")

        if hvac_mode == HVACMode.OFF:
            await self.client.set_command(self.auth, 128, 0)
        else:
            mode_mapping = list(
                mode for mode in CLIMATE_AVAILABLE_MODE if mode["key"] == hvac_mode
            )[0]
            mode = mode_mapping["mappingCode"]
            await self.client.set_command(self.auth, 129, mode)
            if not _is_on:
                await self.client.set_command(self.auth, 128, 1)

        await self.coordinator.async_request_refresh()

    @property
    def preset_mode(self) -> str:
        status = self.coordinator.data[self.index]["status"]
        _is_on = bool(int(status.get("0x00", 0)))
        _hvac_mode = int(status.get("0x01"))
        _preset_mode = (
            HVACMode.OFF if not _is_on else CLIMATE_AVAILABLE_PRESET[_hvac_mode]
        )
        _LOGGER.debug(f"[{self.label}] preset_mode: {_preset_mode}")

        return _preset_mode

    @property
    def preset_modes(self) -> list:
        _preset_modes = list(CLIMATE_AVAILABLE_PRESET.values())
        _LOGGER.debug(f"[{self.label}] preset_modes: {_preset_modes}")
        return _preset_modes

    async def async_set_preset_mode(self, preset_mode) -> None:
        status = self.coordinator.data[self.index]["status"]
        _is_on = bool(int(status.get("0x00", 0)))

        _LOGGER.debug(f"[{self.label}] Set preset mode to: {preset_mode}")

        value = getKeyFromDict(CLIMATE_AVAILABLE_PRESET, preset_mode)
        self.client.set_command(self.auth, 1, value)
        if not _is_on:
            self.client.set_command(self.auth, 0, 1)

        await self.coordinator.async_request_refresh()

    @property
    def fan_mode(self) -> str:
        status = self.coordinator.data[self.index]["status"]
        _fan_mode = int(status.get("0x02", 0))
        _LOGGER.debug(f"[{self.label}] fan_mode: {_fan_mode}")
        return CLIMATE_AVAILABLE_FAN_MODE[_fan_mode]

    @property
    def fan_modes(self) -> list:
        _fan_modes = list(CLIMATE_AVAILABLE_FAN_MODE.values())
        _LOGGER.debug(f"[{self.label}] fan_modes: {_fan_modes}")
        return _fan_modes

    async def async_set_fan_mode(self, fan_mode) -> None:
        """Set new fan mode."""
        _LOGGER.debug(f"[{self.label}] Set fan mode to {fan_mode}")
        mode_id = int(getKeyFromDict(CLIMATE_AVAILABLE_FAN_MODE, fan_mode))
        await self.client.set_command(self.auth, 130, mode_id)
        await self.coordinator.async_request_refresh()

    @property
    def swing_mode(self) -> str:
        status = self.coordinator.data[self.index]["status"]
        _raw_swing_mode = int(status.get("0x0F", 0))
        _swing_mode = CLIMATE_AVAILABLE_SWING_MODE[_raw_swing_mode]
        _LOGGER.debug(f"[{self.label}] swing_mode: {_swing_mode}")
        return _swing_mode

    @property
    def swing_modes(self) -> list:
        _swing_modes = list(CLIMATE_AVAILABLE_SWING_MODE.values())
        _LOGGER.debug(f"[{self.label}] swing_modes: {_swing_modes}")
        return _swing_modes

    async def async_set_swing_mode(self, swing_mode) -> None:
        _LOGGER.debug(f"[{self.label}] Set swing mode to {swing_mode}")
        mode_id = int(getKeyFromDict(CLIMATE_AVAILABLE_SWING_MODE, swing_mode))
        await self.client.set_command(self.auth, 143, mode_id)
        await self.coordinator.async_request_refresh()

    @property
    def target_temperature(self) -> int:
        status = self.coordinator.data[self.index]["status"]
        _target_temperature = float(status.get("0x03", 0))
        _LOGGER.debug(f"[{self.label}] target_temperature: {_target_temperature}")
        return _target_temperature

    async def async_set_temperature(self, **kwargs):
        """ Set new target temperature """
        target_temp = kwargs.get(ATTR_TEMPERATURE)
        _LOGGER.debug(f"[{self.label}] Set temperature to {target_temp}")
        await self.client.set_command(self.auth, 3, int(target_temp))
        await self.coordinator.async_request_refresh()

    @property
    def current_temperature(self) -> int:
        status = self.coordinator.data[self.index]["status"]
        _current_temperature = float(status.get("0x04", 0))
        _LOGGER.debug(f"[{self.label}] current_temperature: {_current_temperature}")
        return _current_temperature

    @property
    def min_temp(self) -> int:
        """ Return the minimum temperature """
        temperature_range = list(
            filter(lambda c: c["CommandType"] == "0x03", self.commands)
        )[0]["Parameters"]
        minimum_temperature = list(filter(lambda t: t[0] == "Min", temperature_range))[
            0
        ][1]
        _LOGGER.debug(f"[{self.label}] min_temp: {minimum_temperature}")

        return minimum_temperature

    @property
    def max_temp(self) -> int:
        """ Return the maximum temperature """
        temperature_range = list(
            filter(lambda c: c["CommandType"] == "0x03", self.commands)
        )[0]["Parameters"]
        maximum_temperature = list(filter(lambda t: t[0] == "Max", temperature_range))[
            0
        ][1]
        _LOGGER.debug(f"[{self.label}] max_temp: {maximum_temperature}")

        return maximum_temperature

    @property
    def target_temperature_step(self) -> float:
        """ Return temperature step """
        return CLIMATE_TEMPERATURE_STEP



class PanasonicERV(PanasonicBaseEntity, ClimateEntity):
    @property
    def available(self) -> bool:
        status = self.coordinator.data[self.index]["status"]
        return status.get("0x00", None) != None

    @property
    def label(self) -> str:
        return f"{self.nickname} {LABEL_ERV}"
    
    @property
    def temperature_unit(self) -> str:
        return UnitOfTemperature.CELSIUS

    @property
    def supported_features(self) -> int:
        features = (
            ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
            | ClimateEntityFeature.PRESET_MODE
            | ClimateEntityFeature.FAN_MODE
        )
        return features
    
    @property
    def hvac_mode(self) -> str:
        status = self.coordinator.data[self.index]["status"]
        _is_on = bool(int(status.get("0x00", 0)))
        if not _is_on:
            _LOGGER.debug(f"[{self.label}] hvac_mode: off")
            return HVACMode.OFF
        else:
            _LOGGER.debug(f"[{self.label}] hvac_mode: fan_only")
            return HVACMode.FAN_ONLY

    @property
    def hvac_modes(self) -> list:
        return [HVACMode.OFF, HVACMode.FAN_ONLY]

    async def async_set_hvac_mode(self, hvac_mode) -> None:
        _LOGGER.debug(f"[{self.label}] set_hvac_mode: {hvac_mode}")

        if hvac_mode == HVACMode.OFF:
            await self.client.set_command(self.auth, 0, 0)
        elif hvac_mode == HVACMode.FAN_ONLY:
            await self.client.set_command(self.auth, 0, 1)
        await self.coordinator.async_request_refresh()

    @property
    def preset_mode(self) -> str:
        status = self.coordinator.data[self.index]["status"]
        raw_mode_list = list(
            filter(lambda c: c["CommandType"] == "0x15", self.commands)
        )[0]["Parameters"]
        _raw_preset_mode = int(status.get("0x15"))
        _preset_mode = list(filter(lambda m: m[1] == _raw_preset_mode, raw_mode_list))[0][0]
        _LOGGER.debug(f"[{self.label}] preset_mode: {_preset_mode}")

        return _preset_mode

    @property
    def preset_modes(self) -> list:
        raw_mode_list = list(
            filter(lambda c: c["CommandType"] == "0x15", self.commands)
        )[0]["Parameters"]

        def mode_extractor(mode):
            return mode[0]

        _preset_modes = list(map(mode_extractor, raw_mode_list))

        _LOGGER.debug(f"[{self.label}] preset_modes: {_preset_modes}")
        return _preset_modes

    async def async_set_preset_mode(self, preset_mode) -> None:
        raw_mode_list = list(
            filter(lambda c: c["CommandType"] == "0x15", self.commands)
        )[0]["Parameters"]
        target_option = list(filter(lambda m: m[0] == preset_mode, raw_mode_list))
        if len(target_option) > 0:
            _LOGGER.debug(f"[{self.label}] Set preset mode to: {preset_mode}")
            mode_id = target_option[0][1]
            await self.client.set_command(self.auth, 21, mode_id)
            await self.coordinator.async_request_refresh()


    @property
    def fan_mode(self) -> str:
        status = self.coordinator.data[self.index]["status"]
        raw_mode_list = list(
            filter(lambda c: c["CommandType"] == "0x56", self.commands)
        )[0]["Parameters"]
        _raw_fan_mode = int(status.get("0x56", 0))
        _fan_mode = list(filter(lambda m: m[1] == _raw_fan_mode, raw_mode_list))[0][0]
        _LOGGER.debug(f"[{self.label}] fan_mode: {_fan_mode}")
        return _fan_mode

    @property
    def fan_modes(self) -> list:
        raw_mode_list = list(
            filter(lambda c: c["CommandType"] == "0x56", self.commands)
        )[0]["Parameters"]

        def mode_extractor(mode):
            return mode[0]

        _fan_modes = list(map(mode_extractor, raw_mode_list))
        _LOGGER.debug(f"[{self.label}] fan_modes: {_fan_modes}")
        return _fan_modes

    async def async_set_fan_mode(self, fan_mode) -> None:
        raw_mode_list = list(
            filter(lambda c: c["CommandType"] == "0x56", self.commands)
        )[0]["Parameters"]
        target_option  = list(filter(lambda m: m[0] == fan_mode, raw_mode_list))
        if len(target_option) > 0:
            _LOGGER.debug(f"[{self.label}] Set fan mode to {fan_mode}")
            mode_id = target_option[0][1]
            await self.client.set_command(self.auth, 86, mode_id)
            await self.coordinator.async_request_refresh()
