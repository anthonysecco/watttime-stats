# WattTime Status for Home Assistant

[![Validate](https://github.com/anthonysecco/watttime-stats/actions/workflows/validate.yml/badge.svg)](https://github.com/anthonysecco/watttime-stats/actions/workflows/validate.yml)
[![Tests](https://github.com/anthonysecco/watttime-stats/actions/workflows/tests.yml/badge.svg)](https://github.com/anthonysecco/watttime-stats/actions/workflows/tests.yml)
[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-donate-yellow.svg)](https://www.buymeacoffee.com/anthonysecco)

How clean is the power from the grid right now, and when will it be cleanest? This integration
brings [WattTime](https://watttime.org/)'s marginal-emissions data into Home Assistant, so you
can run the dishwasher, charge the car, or pre-cool the house when it does the least harm.

> Unofficial. Not affiliated with or endorsed by WattTime.

It replaces Home Assistant's built-in WattTime integration, which no longer works with WattTime's
v3 API ("You must provide a valid signal type"), and adds forecasts and "clean window" sensors.

## What you get

| Entity | What it shows |
|---|---|
| `sensor.watttime_emissions_index` | 0-100: how dirty power is right now compared with the next 24 hours (0 = cleanest). |
| `sensor.watttime_marginal_emissions` | CO2 from the plant that would cover any extra power you use now (g/kWh or lbs/MWh). |
| `binary_sensor.watttime_clean_now` | On while emissions are in the cleanest part of the look-ahead. |
| `sensor.watttime_clean_until` | When the current clean stretch ends. |
| `sensor.watttime_next_clean` | When the next clean stretch starts (attribute `end`). |
| `sensor.watttime_clean_status` | Short text for dashboards and small screens: "Clean until 4:30 PM", "Next clean 1:45 PM – 3:45 PM". |
| `sensor.watttime_cleanest_window` | Start of the cleanest 2-hour stretch ahead (attributes `end`, `average`, `text`). |
| `sensor.watttime_health_damage` | Health cost of the air pollution from extra power use, in USD/MWh. |
| `sensor.watttime_average_emissions` | Average CO2 of all power on the grid right now (paid plans only; published for the wider grid, e.g. all of CAISO, with a delay). |
| `sensor.watttime_clean_threshold` | The cutoff currently used for "clean" (diagnostic). |

Which entities appear depends on your WattTime plan (below).

### Action: `watttime_stats.get_forecast`

Returns the CO2 forecast in 5-minute steps, in your chosen unit. The forecast isn't stored as an
attribute, so it doesn't bloat your database.

```yaml
action: watttime_stats.get_forecast
response_variable: wt
```

```json
{"region": "CAISO_NORTH", "unit": "g/kWh", "generated_at": "...", "forecast": [{"time": "...", "value": 0.0}, ...]}
```

## What your WattTime plan includes

WattTime's free account includes:

- **Everywhere:** the 0-100 emissions index.
- **California ISO North (CAISO_NORTH)**, which covers Northern California, including the Bay Area
  and Sacramento: everything, meaning live emissions, forecasts up to 72 hours, history and health damage.

Paid plans unlock full data in other regions, plus **average emissions** (AOER), which
WattTime publishes only for the wider grid (for example all of CAISO, not CAISO_NORTH). The integration asks WattTime what your account can
access and only creates the entities it can fill. See [WattTime's plans](https://watttime.org/docs-dev/data-plans/).

## Install

1. In HACS, open the menu (⋮) → **Custom repositories**, add
   `https://github.com/anthonysecco/watttime-stats` with type **Integration**.
2. Install **WattTime Status** and restart Home Assistant.
3. **Settings → Devices & services → Add integration → WattTime Status.**

WattTime has no sign-up web page; accounts are created through its API. The setup screen can
create one for you ("Create an account"), or you can sign in with an existing one. The location
defaults to your Home Assistant home and picks your grid region.

## Options

**Settings → Devices & services → WattTime Status → Configure**

| Option | Default | Notes |
|---|---|---|
| CO2 unit | g/kWh | Or lbs/MWh, WattTime's native unit. |
| Cleanest share of the look-ahead | 25% | Matches WattTime's index, where 0-25 is its cleanest quarter. |
| Never call it clean above | 227 g/kWh | Gas plants run about 385-470 g/kWh, so an all-gas day isn't called "clean". |
| Cleanest window length | 2 h | |
| Look ahead | 24 h | Up to 72 h. |

## Reading the numbers

The index and marginal emissions describe the **marginal** plant: the one that would ramp up if you
used more power right now. In California that is usually a gas plant (around 385-480 g/kWh). On
sunny days, though, the grid sometimes has more solar than it can use and throws the extra away.
Extra use is then covered by that spare solar, so the marginal rate drops to about 0.

When the grid sits right at the edge of having spare solar, it can switch back and forth every few
minutes, and the index jumps between about 0 and 60-100 around midday. That's real, not a glitch.
For scheduling, **Clean now** and **Clean until** are steadier, because they follow the forecast.

## Data use and limits

- Updates every 5 minutes: the index, the latest live value, the forecast and the health-damage
  value, so about 4 requests. Logins are cached for 25 minutes, and WattTime allows 3,000 requests
  per 5 minutes.
- Your WattTime username and password are stored in Home Assistant's config entry, like any other
  integration. Diagnostics downloads remove them.

## Development

```bash
pip install -r requirements_test.txt
pytest
ruff check .
```

## 💖 Support

If you found this project useful, consider buying me a coffee. ☕

<a href="https://www.buymeacoffee.com/anthonysecco"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me a Coffee" height="60" width="217"></a>

## AI Disclosure

This project was built largely with AI coding tools (Claude). I directed the design and reviewed the changes, but most of the code and documentation was written by AI. Please review the code before relying on it, and open an issue if you find a problem.

## License

MIT. WattTime data is subject to [WattTime's terms](https://watttime.org/).
