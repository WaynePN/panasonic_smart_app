import asyncio
from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .smartApp import SmartApp
from .const import (
    DATA_CLIENT,
    DATA_COORDINATOR,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    CONF_PROXY,
    CONF_UPDATE_INTERVAL,
    DEFAULT_NAME,
    PLATFORMS,
    DEVICE_STATUS_CODES,
)

_LOGGER: logging.Logger = logging.getLogger(__package__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up this integration using UI."""
    if hass.data.get(DOMAIN) is None:
        hass.data.setdefault(DOMAIN, {})

    username = entry.data.get(CONF_USERNAME)
    password = entry.data.get(CONF_PASSWORD)
    proxy = entry.options.get(CONF_PROXY, '')
    session = async_get_clientsession(hass)
    client = SmartApp(session, username, password, proxy)

    _LOGGER.info("\nLoading your Panasonic devices. This may takes few minutes to complete.\n")
    await client.login()

    async def async_update_data():
        try:
            _LOGGER.info("Updating device info...")
            return await client.get_device_with_info(DEVICE_STATUS_CODES)
        except:
            raise UpdateFailed("Failed while updating device status")

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DEFAULT_NAME,
        update_method=async_update_data,
        update_interval=timedelta(seconds=entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)),
    )

    await coordinator.async_refresh()

    if not coordinator.last_update_success:
        raise ConfigEntryNotReady

    hass.data[DOMAIN][entry.entry_id] = {
        DATA_CLIENT: client,
        DATA_COORDINATOR: coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.add_update_listener(async_reload_entry)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Handle removal of an entry."""
    unloaded = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, platform)
                for platform in PLATFORMS
            ]
        )
    )
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unloaded


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
