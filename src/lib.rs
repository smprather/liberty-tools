use flate2::read::GzDecoder;
use pyo3::exceptions::{PyKeyError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use std::collections::{HashMap, HashSet, VecDeque};
use std::fs::File;
use std::io::{self, BufReader, Read};

#[pyclass]
#[derive(Clone)]
struct Document {
    #[pyo3(get)]
    library_name: String,
    #[pyo3(get)]
    voltage_unit: Option<String>,
    #[pyo3(get)]
    current_unit: Option<String>,
    #[pyo3(get)]
    time_unit: Option<String>,
    /// Second arg of `capacitive_load_unit (1, ff)` -> "ff".
    #[pyo3(get)]
    capacitive_load_unit: Option<String>,
    /// template name -> [variable_1, variable_2, variable_3] from
    /// `lu_table_template` / `power_lut_template` / `output_current_template`.
    templates: Vec<(String, [Option<String>; 3])>,
    /// Ordered library-group simple/complex attributes (technology, delay_model,
    /// nom_*, default_*, thresholds, …) — everything that isn't a sub-group.
    attributes: Vec<(String, String)>,
    /// `normalized_driver_waveform` tables: index_1 = input slew, index_2 =
    /// normalized voltage (0..1), values = time. `name` = driver_waveform_name.
    driver_waveforms: Vec<TimingTableData>,
    cells: Vec<CellData>,
    bus_types: Vec<BusTypeData>,
}

#[pyclass]
#[derive(Clone)]
struct Cell {
    #[pyo3(get)]
    name: String,
    #[pyo3(get)]
    area: Option<f64>,
    pins: Vec<PinData>,
    buses: Vec<BusData>,
    bundles: Vec<BundleData>,
    attributes: Vec<(String, String)>,
    dynamic_currents: Vec<DynamicCurrentData>,
}

#[pyclass]
#[derive(Clone)]
struct Pin {
    #[pyo3(get)]
    name: String,
    #[pyo3(get)]
    direction: Option<String>,
    #[pyo3(get)]
    function: Option<String>,
    timing_arcs: Vec<TimingArcData>,
    internal_powers: Vec<InternalPowerData>,
    attributes: Vec<(String, String)>,
}

/// An `internal_power` group. Despite the Liberty name, the table values are
/// switching **energy** (joules in SI), not power; scale = voltage * current *
/// time unit (see `Document::energy_unit_joules`).
#[pyclass]
#[derive(Clone)]
struct InternalPower {
    #[pyo3(get)]
    related_pin: Option<String>,
    #[pyo3(get)]
    related_pg_pin: Option<String>,
    #[pyo3(get)]
    when: Option<String>,
    tables: Vec<TimingTableData>,
}

#[pyclass]
#[derive(Clone)]
struct Bus {
    #[pyo3(get)]
    name: String,
    #[pyo3(get)]
    direction: Option<String>,
    #[pyo3(get)]
    function: Option<String>,
    #[pyo3(get)]
    bus_type: Option<String>,
    pins: Vec<PinData>,
    timing_arcs: Vec<TimingArcData>,
}

#[pyclass]
#[derive(Clone)]
struct Bundle {
    #[pyo3(get)]
    name: String,
    #[pyo3(get)]
    direction: Option<String>,
    #[pyo3(get)]
    function: Option<String>,
    #[pyo3(get)]
    members: Vec<String>,
    pins: Vec<PinData>,
    timing_arcs: Vec<TimingArcData>,
}

#[pyclass]
#[derive(Clone)]
struct BusType {
    #[pyo3(get)]
    name: String,
    attributes: Vec<(String, String)>,
}

#[pyclass]
#[derive(Clone)]
struct TimingArc {
    #[pyo3(get)]
    related_pin: Option<String>,
    #[pyo3(get)]
    timing_type: Option<String>,
    #[pyo3(get)]
    when: Option<String>,
    tables: Vec<TimingTableData>,
}

#[pyclass]
#[derive(Clone)]
struct TimingTable {
    #[pyo3(get)]
    name: String,
    #[pyo3(get)]
    index_1: Vec<f64>,
    #[pyo3(get)]
    index_2: Vec<f64>,
    #[pyo3(get)]
    index_3: Vec<f64>,
    #[pyo3(get)]
    values: Vec<f64>,
    /// The lookup-table template named in the group header, e.g. `cell_rise
    /// (delay_template_7x7_x1)` -> `delay_template_7x7_x1`. Resolves axis
    /// variable names via `Document::templates`.
    #[pyo3(get)]
    template: Option<String>,
    /// CCS only: the `reference_time` of a `vector` group.
    #[pyo3(get)]
    reference_time: Option<f64>,
    /// CCS only: nested `vector` sub-tables (one current-vs-time wave each) for
    /// `output_current_*` / `ccsn_*` groups. Empty for ordinary NLDM tables.
    vectors: Vec<TimingTableData>,
}

#[derive(Clone)]
struct CellData {
    name: String,
    area: Option<f64>,
    pins: Vec<PinData>,
    buses: Vec<BusData>,
    bundles: Vec<BundleData>,
    attributes: Vec<(String, String)>,
    dynamic_currents: Vec<DynamicCurrentData>,
}

/// CCS power (`dynamic_current`): per-condition power/ground current waveforms.
#[derive(Clone)]
struct DynamicCurrentData {
    related_inputs: Option<String>,
    related_outputs: Option<String>,
    when: Option<String>,
    switching_groups: Vec<SwitchingGroupData>,
}

#[derive(Clone)]
struct SwitchingGroupData {
    input_switching_condition: Option<String>,
    output_switching_condition: Option<String>,
    pg_currents: Vec<PgCurrentData>,
}

#[derive(Clone)]
struct PgCurrentData {
    pg_pin: Option<String>,
    /// One `vector` per (slew, cap): a current-vs-time wave (reuses the timing
    /// table's index_1/2 = slew/cap, index_3 = time, values = current).
    vectors: Vec<TimingTableData>,
}

#[derive(Clone)]
struct PinData {
    name: String,
    direction: Option<String>,
    function: Option<String>,
    timing_arcs: Vec<TimingArcData>,
    internal_powers: Vec<InternalPowerData>,
    attributes: Vec<(String, String)>,
}

#[derive(Clone)]
struct InternalPowerData {
    related_pin: Option<String>,
    related_pg_pin: Option<String>,
    when: Option<String>,
    tables: Vec<TimingTableData>,
}

#[derive(Clone)]
struct BusData {
    name: String,
    direction: Option<String>,
    function: Option<String>,
    bus_type: Option<String>,
    pins: Vec<PinData>,
    timing_arcs: Vec<TimingArcData>,
}

#[derive(Clone)]
struct BundleData {
    name: String,
    direction: Option<String>,
    function: Option<String>,
    members: Vec<String>,
    pins: Vec<PinData>,
    timing_arcs: Vec<TimingArcData>,
}

#[derive(Clone)]
struct BusTypeData {
    name: String,
    attributes: Vec<(String, String)>,
}

#[derive(Clone)]
struct TimingArcData {
    related_pin: Option<String>,
    timing_type: Option<String>,
    when: Option<String>,
    tables: Vec<TimingTableData>,
}

#[derive(Clone)]
struct TimingTableData {
    name: String,
    index_1: Vec<f64>,
    index_2: Vec<f64>,
    index_3: Vec<f64>,
    values: Vec<f64>,
    template: Option<String>,
    reference_time: Option<f64>,
    vectors: Vec<TimingTableData>,
}

impl From<CellData> for Cell {
    fn from(value: CellData) -> Self {
        Self {
            name: value.name,
            area: value.area,
            pins: value.pins,
            buses: value.buses,
            bundles: value.bundles,
            attributes: value.attributes,
            dynamic_currents: value.dynamic_currents,
        }
    }
}

impl From<PinData> for Pin {
    fn from(value: PinData) -> Self {
        Self {
            name: value.name,
            direction: value.direction,
            function: value.function,
            timing_arcs: value.timing_arcs,
            internal_powers: value.internal_powers,
            attributes: value.attributes,
        }
    }
}

impl From<InternalPowerData> for InternalPower {
    fn from(value: InternalPowerData) -> Self {
        Self {
            related_pin: value.related_pin,
            related_pg_pin: value.related_pg_pin,
            when: value.when,
            tables: value.tables,
        }
    }
}

impl From<BusData> for Bus {
    fn from(value: BusData) -> Self {
        Self {
            name: value.name,
            direction: value.direction,
            function: value.function,
            bus_type: value.bus_type,
            pins: value.pins,
            timing_arcs: value.timing_arcs,
        }
    }
}

impl From<BundleData> for Bundle {
    fn from(value: BundleData) -> Self {
        Self {
            name: value.name,
            direction: value.direction,
            function: value.function,
            members: value.members,
            pins: value.pins,
            timing_arcs: value.timing_arcs,
        }
    }
}

impl From<BusTypeData> for BusType {
    fn from(value: BusTypeData) -> Self {
        Self {
            name: value.name,
            attributes: value.attributes,
        }
    }
}

impl From<TimingArcData> for TimingArc {
    fn from(value: TimingArcData) -> Self {
        Self {
            related_pin: value.related_pin,
            timing_type: value.timing_type,
            when: value.when,
            tables: value.tables,
        }
    }
}

impl From<TimingTableData> for TimingTable {
    fn from(value: TimingTableData) -> Self {
        Self {
            name: value.name,
            index_1: value.index_1,
            index_2: value.index_2,
            index_3: value.index_3,
            values: value.values,
            template: value.template,
            reference_time: value.reference_time,
            vectors: value.vectors,
        }
    }
}

#[pymethods]
impl Document {
    fn cells(&self) -> Vec<String> {
        self.cells.iter().map(|cell| cell.name.clone()).collect()
    }

    fn bus_types(&self) -> Vec<String> {
        self.bus_types
            .iter()
            .map(|bus_type| bus_type.name.clone())
            .collect()
    }

    fn bus_type(&self, name: &str) -> PyResult<BusType> {
        self.bus_types
            .iter()
            .find(|bus_type| bus_type.name == name)
            .cloned()
            .map(BusType::from)
            .ok_or_else(|| PyKeyError::new_err(format!("unknown bus type {name:?}")))
    }

    fn cell(&self, name: &str) -> PyResult<Cell> {
        self.cells
            .iter()
            .find(|cell| cell.name == name)
            .cloned()
            .map(Cell::from)
            .ok_or_else(|| PyKeyError::new_err(format!("unknown cell {name:?}")))
    }

    #[pyo3(signature = (cell=None, pin=None, related_pin=None, timing_type=None, when=None, table=None))]
    fn timing_tables<'py>(
        &self,
        py: Python<'py>,
        cell: Option<&str>,
        pin: Option<&str>,
        related_pin: Option<&str>,
        timing_type: Option<&str>,
        when: Option<&str>,
        table: Option<&str>,
    ) -> PyResult<Bound<'py, PyList>> {
        let when_filter = WhenFilter::new(when)?;
        let rows = PyList::empty(py);
        for cell_data in &self.cells {
            if !matches_opt(cell, &cell_data.name) {
                continue;
            }
            for pin_data in &cell_data.pins {
                if !matches_opt(pin, &pin_data.name) {
                    continue;
                }
                for arc in &pin_data.timing_arcs {
                    if !matches_opt_opt(related_pin, arc.related_pin.as_deref())
                        || !matches_opt_opt(timing_type, arc.timing_type.as_deref())
                        || !when_filter.matches(arc.when.as_deref())
                    {
                        continue;
                    }
                    for timing_table in &arc.tables {
                        if !matches_opt(table, &timing_table.name) {
                            continue;
                        }
                        append_table_rows(
                            py,
                            &rows,
                            &cell_data.name,
                            &pin_data.name,
                            arc,
                            timing_table,
                        )?;
                    }
                }
            }
            for bus_data in &cell_data.buses {
                if matches_opt(pin, &bus_data.name) {
                    append_matching_arc_tables(
                        py,
                        &rows,
                        &cell_data.name,
                        &bus_data.name,
                        &bus_data.timing_arcs,
                        related_pin,
                        timing_type,
                        &when_filter,
                        table,
                    )?;
                }
                for pin_data in &bus_data.pins {
                    if !matches_opt(pin, &pin_data.name) {
                        continue;
                    }
                    append_matching_arc_tables(
                        py,
                        &rows,
                        &cell_data.name,
                        &pin_data.name,
                        &pin_data.timing_arcs,
                        related_pin,
                        timing_type,
                        &when_filter,
                        table,
                    )?;
                }
            }
            for bundle_data in &cell_data.bundles {
                if matches_opt(pin, &bundle_data.name) {
                    append_matching_arc_tables(
                        py,
                        &rows,
                        &cell_data.name,
                        &bundle_data.name,
                        &bundle_data.timing_arcs,
                        related_pin,
                        timing_type,
                        &when_filter,
                        table,
                    )?;
                }
                for pin_data in &bundle_data.pins {
                    if !matches_opt(pin, &pin_data.name) {
                        continue;
                    }
                    append_matching_arc_tables(
                        py,
                        &rows,
                        &cell_data.name,
                        &pin_data.name,
                        &pin_data.timing_arcs,
                        related_pin,
                        timing_type,
                        &when_filter,
                        table,
                    )?;
                }
            }
        }
        Ok(rows)
    }

    /// SI scale (joules) for `internal_power` energy values: voltage * current *
    /// time unit. ASAP7 (1V, 1mA, 1ps) -> 1e-15 = femtojoules.
    fn energy_unit_joules(&self) -> Option<f64> {
        Some(
            unit_scale(self.voltage_unit.as_deref()?)?
                * unit_scale(self.current_unit.as_deref()?)?
                * unit_scale(self.time_unit.as_deref()?)?,
        )
    }

    /// Lookup-table templates: name -> [variable_1, variable_2, variable_3].
    /// Used to label table axes with their physical quantity.
    fn templates<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        let map = PyDict::new(py);
        for (name, vars) in &self.templates {
            let list = PyList::empty(py);
            for v in vars {
                list.append(v.as_deref())?;
            }
            map.set_item(name, list)?;
        }
        Ok(map)
    }

    /// Ordered `(name, value)` library-group simple/complex attributes.
    fn attributes(&self) -> Vec<(String, String)> {
        self.attributes.clone()
    }

    /// `normalized_driver_waveform` tables (index_1 = slew, index_2 = normalized
    /// voltage, values = time). `name` holds the driver_waveform_name.
    fn driver_waveforms(&self) -> Vec<TimingTable> {
        self.driver_waveforms
            .iter()
            .cloned()
            .map(TimingTable::from)
            .collect()
    }

    #[pyo3(signature = (cell=None, pin=None, related_pin=None, related_pg_pin=None, when=None, table=None))]
    fn internal_power_tables<'py>(
        &self,
        py: Python<'py>,
        cell: Option<&str>,
        pin: Option<&str>,
        related_pin: Option<&str>,
        related_pg_pin: Option<&str>,
        when: Option<&str>,
        table: Option<&str>,
    ) -> PyResult<Bound<'py, PyList>> {
        let when_filter = WhenFilter::new(when)?;
        let rows = PyList::empty(py);
        for cell_data in &self.cells {
            if !matches_opt(cell, &cell_data.name) {
                continue;
            }
            let mut pin_groups: Vec<&PinData> = cell_data.pins.iter().collect();
            for bus_data in &cell_data.buses {
                pin_groups.extend(bus_data.pins.iter());
            }
            for bundle_data in &cell_data.bundles {
                pin_groups.extend(bundle_data.pins.iter());
            }
            for pin_data in pin_groups {
                if !matches_opt(pin, &pin_data.name) {
                    continue;
                }
                append_matching_power_tables(
                    py,
                    &rows,
                    &cell_data.name,
                    &pin_data.name,
                    &pin_data.internal_powers,
                    related_pin,
                    related_pg_pin,
                    &when_filter,
                    table,
                )?;
            }
        }
        Ok(rows)
    }
}

#[pymethods]
impl Cell {
    fn pins(&self) -> Vec<String> {
        self.pins.iter().map(|pin| pin.name.clone()).collect()
    }

    fn pin(&self, name: &str) -> PyResult<Pin> {
        self.pins
            .iter()
            .find(|pin| pin.name == name)
            .cloned()
            .map(Pin::from)
            .ok_or_else(|| PyKeyError::new_err(format!("unknown pin {name:?}")))
    }

    fn buses(&self) -> Vec<String> {
        self.buses.iter().map(|bus| bus.name.clone()).collect()
    }

    fn bus(&self, name: &str) -> PyResult<Bus> {
        self.buses
            .iter()
            .find(|bus| bus.name == name)
            .cloned()
            .map(Bus::from)
            .ok_or_else(|| PyKeyError::new_err(format!("unknown bus {name:?}")))
    }

    fn bundles(&self) -> Vec<String> {
        self.bundles
            .iter()
            .map(|bundle| bundle.name.clone())
            .collect()
    }

    fn bundle(&self, name: &str) -> PyResult<Bundle> {
        self.bundles
            .iter()
            .find(|bundle| bundle.name == name)
            .cloned()
            .map(Bundle::from)
            .ok_or_else(|| PyKeyError::new_err(format!("unknown bundle {name:?}")))
    }

    /// Ordered `(name, value)` simple/complex attributes of the cell group.
    fn attributes(&self) -> Vec<(String, String)> {
        self.attributes.clone()
    }

    /// CCS power (`dynamic_current`) groups.
    fn dynamic_currents(&self) -> Vec<DynamicCurrent> {
        self.dynamic_currents
            .iter()
            .cloned()
            .map(DynamicCurrent::from)
            .collect()
    }
}

#[pyclass]
#[derive(Clone)]
struct DynamicCurrent {
    #[pyo3(get)]
    related_inputs: Option<String>,
    #[pyo3(get)]
    related_outputs: Option<String>,
    #[pyo3(get)]
    when: Option<String>,
    switching_groups: Vec<SwitchingGroupData>,
}

impl From<DynamicCurrentData> for DynamicCurrent {
    fn from(value: DynamicCurrentData) -> Self {
        Self {
            related_inputs: value.related_inputs,
            related_outputs: value.related_outputs,
            when: value.when,
            switching_groups: value.switching_groups,
        }
    }
}

#[pymethods]
impl DynamicCurrent {
    fn switching_groups(&self) -> Vec<SwitchingGroup> {
        self.switching_groups
            .iter()
            .cloned()
            .map(SwitchingGroup::from)
            .collect()
    }
}

#[pyclass]
#[derive(Clone)]
struct SwitchingGroup {
    #[pyo3(get)]
    input_switching_condition: Option<String>,
    #[pyo3(get)]
    output_switching_condition: Option<String>,
    pg_currents: Vec<PgCurrentData>,
}

impl From<SwitchingGroupData> for SwitchingGroup {
    fn from(value: SwitchingGroupData) -> Self {
        Self {
            input_switching_condition: value.input_switching_condition,
            output_switching_condition: value.output_switching_condition,
            pg_currents: value.pg_currents,
        }
    }
}

#[pymethods]
impl SwitchingGroup {
    fn pg_currents(&self) -> Vec<PgCurrent> {
        self.pg_currents
            .iter()
            .cloned()
            .map(PgCurrent::from)
            .collect()
    }
}

#[pyclass]
#[derive(Clone)]
struct PgCurrent {
    #[pyo3(get)]
    pg_pin: Option<String>,
    vectors: Vec<TimingTableData>,
}

impl From<PgCurrentData> for PgCurrent {
    fn from(value: PgCurrentData) -> Self {
        Self {
            pg_pin: value.pg_pin,
            vectors: value.vectors,
        }
    }
}

#[pymethods]
impl PgCurrent {
    /// One `TimingTable` per (slew, cap) — a current-vs-time wave.
    fn vectors(&self) -> Vec<TimingTable> {
        self.vectors
            .iter()
            .cloned()
            .map(TimingTable::from)
            .collect()
    }
}

#[pymethods]
impl Pin {
    #[pyo3(signature = (related_pin=None, timing_type=None, when=None))]
    fn timing_arcs(
        &self,
        related_pin: Option<&str>,
        timing_type: Option<&str>,
        when: Option<&str>,
    ) -> PyResult<Vec<TimingArc>> {
        filter_timing_arcs(&self.timing_arcs, related_pin, timing_type, when)
    }

    #[pyo3(signature = (related_pin=None, related_pg_pin=None, when=None))]
    fn internal_power(
        &self,
        related_pin: Option<&str>,
        related_pg_pin: Option<&str>,
        when: Option<&str>,
    ) -> PyResult<Vec<InternalPower>> {
        let when_filter = WhenFilter::new(when)?;
        Ok(self
            .internal_powers
            .iter()
            .filter(|group| {
                matches_opt_opt(related_pin, group.related_pin.as_deref())
                    && matches_opt_opt(related_pg_pin, group.related_pg_pin.as_deref())
                    && when_filter.matches(group.when.as_deref())
            })
            .cloned()
            .map(InternalPower::from)
            .collect())
    }

    /// Ordered `(name, value)` simple/complex attributes of the pin group.
    fn attributes(&self) -> Vec<(String, String)> {
        self.attributes.clone()
    }
}

#[pymethods]
impl InternalPower {
    fn tables(&self) -> Vec<String> {
        self.tables.iter().map(|table| table.name.clone()).collect()
    }

    fn table(&self, name: &str) -> PyResult<TimingTable> {
        self.tables
            .iter()
            .find(|table| table.name == name)
            .cloned()
            .map(TimingTable::from)
            .ok_or_else(|| PyKeyError::new_err(format!("unknown power table {name:?}")))
    }
}

#[pymethods]
impl Bus {
    fn pins(&self) -> Vec<String> {
        self.pins.iter().map(|pin| pin.name.clone()).collect()
    }

    fn pin(&self, name: &str) -> PyResult<Pin> {
        self.pins
            .iter()
            .find(|pin| pin.name == name)
            .cloned()
            .map(Pin::from)
            .ok_or_else(|| PyKeyError::new_err(format!("unknown bus pin {name:?}")))
    }

    #[pyo3(signature = (related_pin=None, timing_type=None, when=None))]
    fn timing_arcs(
        &self,
        related_pin: Option<&str>,
        timing_type: Option<&str>,
        when: Option<&str>,
    ) -> PyResult<Vec<TimingArc>> {
        filter_timing_arcs(&self.timing_arcs, related_pin, timing_type, when)
    }
}

#[pymethods]
impl Bundle {
    fn pins(&self) -> Vec<String> {
        self.pins.iter().map(|pin| pin.name.clone()).collect()
    }

    fn pin(&self, name: &str) -> PyResult<Pin> {
        self.pins
            .iter()
            .find(|pin| pin.name == name)
            .cloned()
            .map(Pin::from)
            .ok_or_else(|| PyKeyError::new_err(format!("unknown bundle pin {name:?}")))
    }

    #[pyo3(signature = (related_pin=None, timing_type=None, when=None))]
    fn timing_arcs(
        &self,
        related_pin: Option<&str>,
        timing_type: Option<&str>,
        when: Option<&str>,
    ) -> PyResult<Vec<TimingArc>> {
        filter_timing_arcs(&self.timing_arcs, related_pin, timing_type, when)
    }
}

#[pymethods]
impl BusType {
    fn attributes<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        let attrs = PyDict::new(py);
        for (key, value) in &self.attributes {
            attrs.set_item(key, value)?;
        }
        Ok(attrs)
    }

    fn get(&self, key: &str) -> Option<String> {
        self.attributes
            .iter()
            .find(|(name, _)| name == key)
            .map(|(_, value)| value.clone())
    }
}

#[pymethods]
impl TimingArc {
    fn tables(&self) -> Vec<String> {
        self.tables.iter().map(|table| table.name.clone()).collect()
    }

    fn table(&self, name: &str) -> PyResult<TimingTable> {
        self.tables
            .iter()
            .find(|table| table.name == name)
            .cloned()
            .map(TimingTable::from)
            .ok_or_else(|| PyKeyError::new_err(format!("unknown timing table {name:?}")))
    }
}

#[pymethods]
impl TimingTable {
    /// CCS `vector` sub-tables (current-vs-time waves). Empty for NLDM tables.
    fn vectors(&self) -> Vec<TimingTable> {
        self.vectors
            .iter()
            .cloned()
            .map(TimingTable::from)
            .collect()
    }

    fn rows<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyList>> {
        let rows = PyList::empty(py);
        append_table_rows(
            py,
            &rows,
            "",
            "",
            &TimingArcData {
                related_pin: None,
                timing_type: None,
                when: None,
                tables: Vec::new(),
            },
            &TimingTableData {
                name: self.name.clone(),
                index_1: self.index_1.clone(),
                index_2: self.index_2.clone(),
                index_3: self.index_3.clone(),
                values: self.values.clone(),
                template: self.template.clone(),
                reference_time: self.reference_time,
                vectors: Vec::new(),
            },
        )?;
        Ok(rows)
    }
}

#[pyfunction]
#[pyo3(signature = (path, cells=None))]
fn parse_file(path: &str, cells: Option<Vec<String>>) -> PyResult<Document> {
    let filter = cells.map(|items| items.into_iter().collect::<HashSet<_>>());
    let reader = open_input(path).map_err(|err| PyValueError::new_err(err.to_string()))?;
    let mut parser = Parser::new(reader, filter).map_err(ParseError::into_py)?;
    parser.parse_document().map_err(ParseError::into_py)
}

/// Encode the lexer's token stream as strings (`W<value>` for words, `S<char>`
/// for symbols). Comments and whitespace are not tokens, so two files with
/// equal token streams parse identically — the basis for `liberty_format`'s
/// functional-transparency guarantee.
fn lex_all(reader: Box<dyn Read>) -> Result<Vec<String>, ParseError> {
    let mut lexer = Lexer::new(reader)?;
    let mut out = Vec::new();
    while let Some(tok) = lexer.next_token()? {
        match tok.kind {
            TokenKind::Word(v) => out.push(format!("W{v}")),
            TokenKind::Symbol(b) => out.push(format!("S{}", b as char)),
        }
    }
    Ok(out)
}

#[pyfunction]
fn tokenize(path: &str) -> PyResult<Vec<String>> {
    let reader = open_input(path).map_err(|err| PyValueError::new_err(err.to_string()))?;
    lex_all(reader).map_err(ParseError::into_py)
}

#[pyfunction]
fn tokenize_str(text: &str) -> PyResult<Vec<String>> {
    let reader: Box<dyn Read> = Box::new(io::Cursor::new(text.as_bytes().to_vec()));
    lex_all(reader).map_err(ParseError::into_py)
}

#[pymodule]
fn _native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<Document>()?;
    m.add_class::<Cell>()?;
    m.add_class::<Pin>()?;
    m.add_class::<Bus>()?;
    m.add_class::<Bundle>()?;
    m.add_class::<BusType>()?;
    m.add_class::<TimingArc>()?;
    m.add_class::<TimingTable>()?;
    m.add_class::<InternalPower>()?;
    m.add_class::<DynamicCurrent>()?;
    m.add_class::<SwitchingGroup>()?;
    m.add_class::<PgCurrent>()?;
    m.add_class::<LibraryIndex>()?;
    m.add_function(wrap_pyfunction!(parse_file, m)?)?;
    m.add_function(wrap_pyfunction!(tokenize, m)?)?;
    m.add_function(wrap_pyfunction!(tokenize_str, m)?)?;
    Ok(())
}

fn append_table_rows<'py>(
    py: Python<'py>,
    rows: &Bound<'py, PyList>,
    cell: &str,
    pin: &str,
    arc: &TimingArcData,
    table: &TimingTableData,
) -> PyResult<()> {
    for (idx, value) in table.values.iter().enumerate() {
        let row = PyDict::new(py);
        row.set_item("cell", cell)?;
        row.set_item("pin", pin)?;
        row.set_item("related_pin", arc.related_pin.as_deref())?;
        row.set_item("timing_type", arc.timing_type.as_deref())?;
        row.set_item("when", arc.when.as_deref())?;
        row.set_item("table", &table.name)?;
        let (i, j, k) = table_position(table, idx);
        row.set_item("index_1", table.index_1.get(i).copied())?;
        row.set_item("index_2", table.index_2.get(j).copied())?;
        row.set_item("index_3", table.index_3.get(k).copied())?;
        row.set_item("row", i)?;
        row.set_item("col", j)?;
        row.set_item("depth", k)?;
        row.set_item("value", value)?;
        rows.append(row)?;
    }
    Ok(())
}

fn append_matching_arc_tables<'py>(
    py: Python<'py>,
    rows: &Bound<'py, PyList>,
    cell: &str,
    pin: &str,
    arcs: &[TimingArcData],
    related_pin: Option<&str>,
    timing_type: Option<&str>,
    when_filter: &WhenFilter,
    table: Option<&str>,
) -> PyResult<()> {
    for arc in arcs {
        if !matches_opt_opt(related_pin, arc.related_pin.as_deref())
            || !matches_opt_opt(timing_type, arc.timing_type.as_deref())
            || !when_filter.matches(arc.when.as_deref())
        {
            continue;
        }
        for timing_table in &arc.tables {
            if matches_opt(table, &timing_table.name) {
                append_table_rows(py, rows, cell, pin, arc, timing_table)?;
            }
        }
    }
    Ok(())
}

#[allow(clippy::too_many_arguments)]
fn append_matching_power_tables<'py>(
    py: Python<'py>,
    rows: &Bound<'py, PyList>,
    cell: &str,
    pin: &str,
    groups: &[InternalPowerData],
    related_pin: Option<&str>,
    related_pg_pin: Option<&str>,
    when_filter: &WhenFilter,
    table: Option<&str>,
) -> PyResult<()> {
    for group in groups {
        if !matches_opt_opt(related_pin, group.related_pin.as_deref())
            || !matches_opt_opt(related_pg_pin, group.related_pg_pin.as_deref())
            || !when_filter.matches(group.when.as_deref())
        {
            continue;
        }
        for power_table in &group.tables {
            if !matches_opt(table, &power_table.name) {
                continue;
            }
            for (idx, value) in power_table.values.iter().enumerate() {
                let row = PyDict::new(py);
                row.set_item("cell", cell)?;
                row.set_item("pin", pin)?;
                row.set_item("related_pin", group.related_pin.as_deref())?;
                row.set_item("related_pg_pin", group.related_pg_pin.as_deref())?;
                row.set_item("when", group.when.as_deref())?;
                row.set_item("table", &power_table.name)?;
                let (i, j, k) = table_position(power_table, idx);
                row.set_item("index_1", power_table.index_1.get(i).copied())?;
                row.set_item("index_2", power_table.index_2.get(j).copied())?;
                row.set_item("index_3", power_table.index_3.get(k).copied())?;
                row.set_item("row", i)?;
                row.set_item("col", j)?;
                row.set_item("depth", k)?;
                row.set_item("value", value)?;
                rows.append(row)?;
            }
        }
    }
    Ok(())
}

fn table_position(table: &TimingTableData, idx: usize) -> (usize, usize, usize) {
    if !table.index_3.is_empty() {
        let n3 = table.index_3.len();
        let n2 = table.index_2.len().max(1);
        let plane = n2 * n3;
        (idx / plane, (idx % plane) / n3, idx % n3)
    } else if !table.index_2.is_empty() {
        let n2 = table.index_2.len();
        (idx / n2, idx % n2, 0)
    } else if !table.index_1.is_empty() {
        (idx, 0, 0)
    } else {
        (0, idx, 0)
    }
}

fn filter_timing_arcs(
    arcs: &[TimingArcData],
    related_pin: Option<&str>,
    timing_type: Option<&str>,
    when: Option<&str>,
) -> PyResult<Vec<TimingArc>> {
    let when_filter = WhenFilter::new(when)?;
    Ok(arcs
        .iter()
        .filter(|arc| {
            matches_opt_opt(related_pin, arc.related_pin.as_deref())
                && matches_opt_opt(timing_type, arc.timing_type.as_deref())
                && when_filter.matches(arc.when.as_deref())
        })
        .cloned()
        .map(TimingArc::from)
        .collect())
}

fn matches_opt(filter: Option<&str>, actual: &str) -> bool {
    filter.map_or(true, |value| value == actual)
}

fn matches_opt_opt(filter: Option<&str>, actual: Option<&str>) -> bool {
    filter.map_or(true, |value| actual == Some(value))
}

struct WhenFilter {
    query: Option<BoolExpr>,
}

impl WhenFilter {
    fn new(query: Option<&str>) -> PyResult<Self> {
        let query = query
            .map(parse_bool_expr)
            .transpose()
            .map_err(|err| PyValueError::new_err(format!("invalid when expression: {err}")))?;
        Ok(Self { query })
    }

    fn matches(&self, actual: Option<&str>) -> bool {
        let Some(query) = &self.query else {
            return true;
        };
        let Some(actual) = actual else {
            return false;
        };
        parse_bool_expr(actual)
            .map(|actual| bool_implies(&actual, query))
            .unwrap_or(false)
    }
}

#[derive(Clone, Debug)]
enum BoolExpr {
    Var(String),
    Const(bool),
    Not(Box<BoolExpr>),
    And(Box<BoolExpr>, Box<BoolExpr>),
    Or(Box<BoolExpr>, Box<BoolExpr>),
    Xor(Box<BoolExpr>, Box<BoolExpr>),
}

impl BoolExpr {
    fn eval(&self, true_vars: &HashSet<String>) -> bool {
        match self {
            BoolExpr::Var(name) => true_vars.contains(name),
            BoolExpr::Const(value) => *value,
            BoolExpr::Not(expr) => !expr.eval(true_vars),
            BoolExpr::And(left, right) => left.eval(true_vars) && right.eval(true_vars),
            BoolExpr::Or(left, right) => left.eval(true_vars) || right.eval(true_vars),
            BoolExpr::Xor(left, right) => left.eval(true_vars) ^ right.eval(true_vars),
        }
    }

    fn collect_vars(&self, vars: &mut Vec<String>) {
        match self {
            BoolExpr::Var(name) => {
                if !vars.iter().any(|item| item == name) {
                    vars.push(name.clone());
                }
            }
            BoolExpr::Const(_) => {}
            BoolExpr::Not(expr) => expr.collect_vars(vars),
            BoolExpr::And(left, right) | BoolExpr::Or(left, right) | BoolExpr::Xor(left, right) => {
                left.collect_vars(vars);
                right.collect_vars(vars);
            }
        }
    }
}

fn bool_implies(actual: &BoolExpr, query: &BoolExpr) -> bool {
    let mut vars = Vec::new();
    actual.collect_vars(&mut vars);
    query.collect_vars(&mut vars);
    let assignment_count = 1usize.checked_shl(vars.len() as u32).unwrap_or(0);
    if assignment_count == 0 {
        return false;
    }

    for mask in 0..assignment_count {
        let mut true_vars = HashSet::new();
        for (idx, name) in vars.iter().enumerate() {
            if (mask & (1usize << idx)) != 0 {
                true_vars.insert(name.clone());
            }
        }
        if actual.eval(&true_vars) && !query.eval(&true_vars) {
            return false;
        }
    }
    true
}

fn parse_bool_expr(input: &str) -> Result<BoolExpr, String> {
    let mut parser = BoolParser::new(input);
    let expr = parser.parse_or()?;
    parser.skip_ws();
    if parser.is_eof() {
        Ok(expr)
    } else {
        Err(format!("unexpected token at byte {}", parser.pos))
    }
}

struct BoolParser<'a> {
    input: &'a str,
    pos: usize,
}

impl<'a> BoolParser<'a> {
    fn new(input: &'a str) -> Self {
        Self { input, pos: 0 }
    }

    fn parse_or(&mut self) -> Result<BoolExpr, String> {
        let mut expr = self.parse_xor()?;
        loop {
            self.skip_ws();
            if self.consume('|') || self.consume('+') {
                let right = self.parse_xor()?;
                expr = BoolExpr::Or(Box::new(expr), Box::new(right));
            } else {
                return Ok(expr);
            }
        }
    }

    fn parse_xor(&mut self) -> Result<BoolExpr, String> {
        let mut expr = self.parse_and()?;
        loop {
            self.skip_ws();
            if self.consume('^') {
                let right = self.parse_and()?;
                expr = BoolExpr::Xor(Box::new(expr), Box::new(right));
            } else {
                return Ok(expr);
            }
        }
    }

    fn parse_and(&mut self) -> Result<BoolExpr, String> {
        let mut expr = self.parse_not()?;
        loop {
            self.skip_ws();
            if self.consume('&') || self.consume('*') {
                let right = self.parse_not()?;
                expr = BoolExpr::And(Box::new(expr), Box::new(right));
            } else {
                return Ok(expr);
            }
        }
    }

    fn parse_not(&mut self) -> Result<BoolExpr, String> {
        self.skip_ws();
        if self.consume('!') || self.consume('~') {
            Ok(BoolExpr::Not(Box::new(self.parse_not()?)))
        } else {
            let mut expr = self.parse_primary()?;
            loop {
                self.skip_ws();
                if self.consume('\'') {
                    expr = BoolExpr::Not(Box::new(expr));
                } else {
                    return Ok(expr);
                }
            }
        }
    }

    fn parse_primary(&mut self) -> Result<BoolExpr, String> {
        self.skip_ws();
        if self.consume('(') {
            let expr = self.parse_or()?;
            self.skip_ws();
            if !self.consume(')') {
                return Err(format!("expected ')' at byte {}", self.pos));
            }
            return Ok(expr);
        }
        let ident = self.parse_ident()?;
        match ident.as_str() {
            "1" | "true" | "TRUE" => Ok(BoolExpr::Const(true)),
            "0" | "false" | "FALSE" => Ok(BoolExpr::Const(false)),
            _ => Ok(BoolExpr::Var(ident)),
        }
    }

    fn parse_ident(&mut self) -> Result<String, String> {
        self.skip_ws();
        let start = self.pos;
        while let Some(ch) = self.peek() {
            if ch.is_whitespace()
                || matches!(
                    ch,
                    '!' | '~' | '&' | '*' | '|' | '+' | '^' | '\'' | '(' | ')'
                )
            {
                break;
            }
            self.pos += ch.len_utf8();
        }
        if self.pos == start {
            Err(format!("expected identifier at byte {}", self.pos))
        } else {
            Ok(self.input[start..self.pos].to_string())
        }
    }

    fn skip_ws(&mut self) {
        while matches!(self.peek(), Some(ch) if ch.is_whitespace()) {
            self.pos += self.peek().unwrap().len_utf8();
        }
    }

    fn consume(&mut self, expected: char) -> bool {
        if self.peek() == Some(expected) {
            self.pos += expected.len_utf8();
            true
        } else {
            false
        }
    }

    fn peek(&self) -> Option<char> {
        self.input[self.pos..].chars().next()
    }

    fn is_eof(&self) -> bool {
        self.pos >= self.input.len()
    }
}

fn open_input(path: &str) -> io::Result<Box<dyn Read>> {
    let file = File::open(path)?;
    let reader = BufReader::with_capacity(128 * 1024, file);
    if path.ends_with(".gz") {
        Ok(Box::new(GzDecoder::new(reader)))
    } else {
        Ok(Box::new(reader))
    }
}

// ---- byte-offset cell indexing (lazy-parse backend) ------------------------
//
// Scan the whole (decompressed) file once, recording the byte range of every
// top-level `cell (...) {...}` group, so the viewer can list cells and parse one
// at a time instead of parsing the entire file up front. The scanner is lexer-
// faithful about strings/comments but does *not* build any AST.

fn read_to_memory(path: &str) -> io::Result<Vec<u8>> {
    let mut buf = Vec::new();
    open_input(path)?.read_to_end(&mut buf)?;
    Ok(buf)
}

fn is_index_symbol(b: u8) -> bool {
    matches!(b, b'(' | b')' | b'{' | b'}' | b':' | b';' | b',')
}

/// Skip whitespace, `#`/`//`/`* */` comments, and `\`+newline continuations.
fn skip_trivia(d: &[u8], mut i: usize) -> usize {
    let n = d.len();
    loop {
        while i < n && d[i].is_ascii_whitespace() {
            i += 1;
        }
        if i + 1 < n && d[i] == b'\\' && (d[i + 1] == b'\n' || d[i + 1] == b'\r') {
            i += 2;
        } else if i < n && d[i] == b'#' {
            while i < n && d[i] != b'\n' {
                i += 1;
            }
        } else if i + 1 < n && d[i] == b'/' && d[i + 1] == b'/' {
            while i < n && d[i] != b'\n' {
                i += 1;
            }
        } else if i + 1 < n && d[i] == b'/' && d[i + 1] == b'*' {
            i += 2;
            while i + 1 < n && !(d[i] == b'*' && d[i + 1] == b'/') {
                i += 1;
            }
            i = (i + 2).min(n);
        } else {
            break;
        }
    }
    i
}

/// Consume a quoted string starting at `d[i] == quote`; return index after the
/// closing quote, honoring backslash escapes.
fn skip_quoted(d: &[u8], mut i: usize) -> usize {
    let n = d.len();
    let quote = d[i];
    i += 1;
    while i < n {
        if d[i] == b'\\' {
            i += 2;
            continue;
        }
        if d[i] == quote {
            return i + 1;
        }
        i += 1;
    }
    i
}

/// Read one token (bare word or quoted string) at `i`; return (value, next).
fn read_token(d: &[u8], i: usize) -> (String, usize) {
    let n = d.len();
    if i < n && (d[i] == b'"' || d[i] == b'\'') {
        let end = skip_quoted(d, i);
        let inner = &d[i + 1..end.saturating_sub(1).max(i + 1)];
        return (String::from_utf8_lossy(inner).into_owned(), end);
    }
    let start = i;
    let mut j = i;
    while j < n && !d[j].is_ascii_whitespace() && !is_index_symbol(d[j]) {
        j += 1;
    }
    (String::from_utf8_lossy(&d[start..j]).into_owned(), j)
}

/// At `d[i] == '('`, read the comma-separated args (quotes stripped); return
/// (args, index after the matching ')').
fn read_paren_args(d: &[u8], mut i: usize) -> (Vec<String>, usize) {
    let n = d.len();
    i += 1; // past '('
    let mut args = Vec::new();
    let mut cur = String::new();
    while i < n {
        i = skip_trivia(d, i);
        if i >= n {
            break;
        }
        match d[i] {
            b')' => {
                i += 1;
                break;
            }
            b',' => {
                args.push(cur.trim().to_string());
                cur.clear();
                i += 1;
            }
            b'"' | b'\'' => {
                let end = skip_quoted(d, i);
                cur.push_str(&String::from_utf8_lossy(
                    &d[i + 1..end.saturating_sub(1).max(i + 1)],
                ));
                i = end;
            }
            _ => {
                cur.push(d[i] as char);
                i += 1;
            }
        }
    }
    if !cur.trim().is_empty() || !args.is_empty() {
        args.push(cur.trim().to_string());
    }
    (args, i)
}

/// At `d[i] == '{'`, return the index just past the matching `}` (string/comment
/// aware).
fn match_braces(d: &[u8], mut i: usize) -> usize {
    let n = d.len();
    let mut depth = 0usize;
    while i < n {
        match d[i] {
            b'"' | b'\'' => i = skip_quoted(d, i),
            b'#' => {
                while i < n && d[i] != b'\n' {
                    i += 1;
                }
            }
            b'/' if i + 1 < n && d[i + 1] == b'/' => {
                while i < n && d[i] != b'\n' {
                    i += 1;
                }
            }
            b'/' if i + 1 < n && d[i + 1] == b'*' => {
                i += 2;
                while i + 1 < n && !(d[i] == b'*' && d[i + 1] == b'/') {
                    i += 1;
                }
                i = (i + 2).min(n);
            }
            b'{' => {
                depth += 1;
                i += 1;
            }
            b'}' => {
                depth -= 1;
                i += 1;
                if depth == 0 {
                    return i;
                }
            }
            _ => i += 1,
        }
    }
    i
}

fn skip_to_semicolon(d: &[u8], mut i: usize) -> usize {
    let n = d.len();
    while i < n {
        match d[i] {
            b'"' | b'\'' => i = skip_quoted(d, i),
            b';' => return i + 1,
            _ => i += 1,
        }
    }
    i
}

/// Index every top-level `cell` group. Returns (library_name, preamble_start,
/// preamble_end, [(cell_name, start, end)]). Lenient: a stray `}` that drops
/// depth early does not stop cell discovery.
fn index_cells(d: &[u8]) -> (String, usize, usize, Vec<(String, usize, usize)>) {
    let n = d.len();
    let mut i = skip_trivia(d, 0);
    let (_kw, j) = read_token(d, i);
    i = skip_trivia(d, j);
    let mut lib_name = String::new();
    if i < n && d[i] == b'(' {
        let (args, k) = read_paren_args(d, i);
        lib_name = args.into_iter().next().unwrap_or_default();
        i = skip_trivia(d, k);
    }
    if i < n && d[i] == b'{' {
        i += 1;
    }
    let body_start = i;
    let mut cells = Vec::new();
    let mut first_cell: Option<usize> = None;
    while i < n {
        i = skip_trivia(d, i);
        if i >= n {
            break;
        }
        if d[i] == b'}' {
            i += 1; // library close or stray — keep scanning
            continue;
        }
        let tok_start = i;
        let (name, j) = read_token(d, i);
        if name.is_empty() {
            i += 1;
            continue;
        }
        i = skip_trivia(d, j);
        if i < n && d[i] == b'(' {
            let (args, k) = read_paren_args(d, i);
            i = skip_trivia(d, k);
            if i < n && d[i] == b'{' {
                let end = match_braces(d, i);
                if name == "cell" {
                    if first_cell.is_none() {
                        first_cell = Some(tok_start);
                    }
                    cells.push((args.into_iter().next().unwrap_or_default(), tok_start, end));
                }
                i = end;
                let s = skip_trivia(d, i);
                if s < n && d[s] == b';' {
                    i = s + 1;
                }
            } else if i < n && d[i] == b';' {
                i += 1;
            }
        } else if i < n && d[i] == b':' {
            i = skip_to_semicolon(d, i + 1);
        } else {
            i += 1;
        }
    }
    let header_end = first_cell.unwrap_or(i);
    (lib_name, body_start, header_end, cells)
}

fn parse_slice_as_library(name: &str, body: &[u8]) -> Result<Document, ParseError> {
    let mut buf = Vec::with_capacity(body.len() + 32);
    buf.extend_from_slice(format!("library ({name}) {{\n").as_bytes());
    buf.extend_from_slice(body);
    buf.extend_from_slice(b"\n}\n");
    let reader: Box<dyn Read> = Box::new(io::Cursor::new(buf));
    Parser::new(reader, None)?.parse_document()
}

/// Cell-offset index over an in-memory Liberty file: list cells cheaply, parse
/// one cell at a time. Built for multi-GB files where a full parse is too slow.
#[pyclass]
struct LibraryIndex {
    data: Vec<u8>,
    #[pyo3(get)]
    library_name: String,
    order: Vec<String>,
    ranges: HashMap<String, (usize, usize)>,
    header: Document,
}

#[pymethods]
impl LibraryIndex {
    #[staticmethod]
    fn open(path: &str) -> PyResult<LibraryIndex> {
        let data = read_to_memory(path).map_err(|e| PyValueError::new_err(e.to_string()))?;
        let (lib_name, preamble_start, preamble_end, cells) = index_cells(&data);
        let header = parse_slice_as_library(&lib_name, &data[preamble_start..preamble_end])
            .map_err(ParseError::into_py)?;
        let mut order = Vec::with_capacity(cells.len());
        let mut ranges = HashMap::with_capacity(cells.len());
        for (name, start, end) in cells {
            if !ranges.contains_key(&name) {
                order.push(name.clone());
            }
            ranges.insert(name, (start, end));
        }
        Ok(LibraryIndex {
            data,
            library_name: lib_name,
            order,
            ranges,
            header,
        })
    }

    fn cell_names(&self) -> Vec<String> {
        self.order.clone()
    }

    fn num_cells(&self) -> usize {
        self.order.len()
    }

    fn cell(&self, name: &str) -> PyResult<Cell> {
        let &(start, end) = self
            .ranges
            .get(name)
            .ok_or_else(|| PyKeyError::new_err(format!("unknown cell {name:?}")))?;
        let doc = parse_slice_as_library(&self.library_name, &self.data[start..end])
            .map_err(ParseError::into_py)?;
        doc.cells
            .into_iter()
            .next()
            .map(Cell::from)
            .ok_or_else(|| PyValueError::new_err(format!("failed to parse cell {name:?}")))
    }

    // -- library header pass-throughs (parsed once at open) --
    #[getter]
    fn voltage_unit(&self) -> Option<String> {
        self.header.voltage_unit.clone()
    }
    #[getter]
    fn current_unit(&self) -> Option<String> {
        self.header.current_unit.clone()
    }
    #[getter]
    fn time_unit(&self) -> Option<String> {
        self.header.time_unit.clone()
    }
    #[getter]
    fn capacitive_load_unit(&self) -> Option<String> {
        self.header.capacitive_load_unit.clone()
    }
    fn energy_unit_joules(&self) -> Option<f64> {
        self.header.energy_unit_joules()
    }
    fn templates<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        self.header.templates(py)
    }
    fn attributes(&self) -> Vec<(String, String)> {
        self.header.attributes()
    }
    fn driver_waveforms(&self) -> Vec<TimingTable> {
        self.header.driver_waveforms()
    }
}

#[derive(Debug, Clone)]
enum TokenKind {
    Word(String),
    Symbol(u8),
}

#[derive(Debug, Clone)]
struct Token {
    kind: TokenKind,
    line: usize,
    column: usize,
}

struct Lexer {
    reader: Box<dyn Read>,
    peeked: VecDeque<u8>,
    line: usize,
    column: usize,
    eof: bool,
}

impl Lexer {
    fn new(reader: Box<dyn Read>) -> Result<Self, ParseError> {
        Ok(Self {
            reader,
            peeked: VecDeque::new(),
            line: 1,
            column: 1,
            eof: false,
        })
    }

    fn next_token(&mut self) -> Result<Option<Token>, ParseError> {
        self.skip_ws_and_comments()?;
        if self.peek()?.is_none() {
            return Ok(None);
        }

        let line = self.line;
        let column = self.column;
        let byte = self.bump()?.unwrap();
        if is_symbol(byte) {
            return Ok(Some(Token {
                kind: TokenKind::Symbol(byte),
                line,
                column,
            }));
        }
        if byte == b'"' || byte == b'\'' {
            let value = self.read_quoted(byte, line, column)?;
            return Ok(Some(Token {
                kind: TokenKind::Word(value),
                line,
                column,
            }));
        }

        let mut value = Vec::new();
        value.push(byte);
        while let Some(next) = self.peek()? {
            if next.is_ascii_whitespace() || is_symbol(next) {
                break;
            }
            if next == b'/' && matches!(self.peek_next()?, Some(b'*' | b'/')) {
                break;
            }
            if next == b'\\' {
                self.bump()?;
                match self.peek()? {
                    Some(b'\n') => {
                        self.bump()?;
                    }
                    Some(b'\r') => {
                        self.bump()?;
                        if self.peek()? == Some(b'\n') {
                            self.bump()?;
                        }
                    }
                    Some(escaped) => {
                        value.push(b'\\');
                        value.push(escaped);
                        self.bump()?;
                    }
                    None => value.push(b'\\'),
                }
                continue;
            }
            value.push(self.bump()?.unwrap());
        }

        Ok(Some(Token {
            kind: TokenKind::Word(String::from_utf8_lossy(&value).into_owned()),
            line,
            column,
        }))
    }

    fn read_quoted(
        &mut self,
        quote: u8,
        start_line: usize,
        start_column: usize,
    ) -> Result<String, ParseError> {
        let mut value = Vec::new();
        let mut escaped = false;
        while let Some(byte) = self.bump()? {
            if escaped {
                match byte {
                    b'\n' => {}
                    b'\r' => {
                        if self.peek()? == Some(b'\n') {
                            self.bump()?;
                        }
                    }
                    _ => value.push(byte),
                }
                escaped = false;
                continue;
            }
            if byte == b'\\' {
                escaped = true;
                continue;
            }
            if byte == quote {
                return Ok(String::from_utf8_lossy(&value).into_owned());
            }
            value.push(byte);
        }
        Err(ParseError::new(
            start_line,
            start_column,
            "unterminated quoted string",
        ))
    }

    fn skip_ws_and_comments(&mut self) -> Result<(), ParseError> {
        loop {
            loop {
                if matches!(self.peek()?, Some(byte) if byte.is_ascii_whitespace()) {
                    self.bump()?;
                } else if self.peek()? == Some(b'\\')
                    && matches!(self.peek_next()?, Some(b'\n' | b'\r'))
                {
                    self.bump()?;
                    if self.peek()? == Some(b'\r') {
                        self.bump()?;
                        if self.peek()? == Some(b'\n') {
                            self.bump()?;
                        }
                    } else {
                        self.bump()?;
                    }
                } else {
                    break;
                }
            }
            match (self.peek()?, self.peek_next()?) {
                (Some(b'#'), _) => self.skip_line(),
                (Some(b'/'), Some(b'/')) => {
                    self.bump()?;
                    self.bump()?;
                    self.skip_line();
                }
                (Some(b'/'), Some(b'*')) => {
                    let line = self.line;
                    let column = self.column;
                    self.bump()?;
                    self.bump()?;
                    self.skip_block_comment(line, column)?;
                }
                _ => return Ok(()),
            }
        }
    }

    fn skip_line(&mut self) {
        while let Ok(Some(byte)) = self.bump() {
            if byte == b'\n' {
                break;
            }
        }
    }

    fn skip_block_comment(&mut self, line: usize, column: usize) -> Result<(), ParseError> {
        let mut prev = 0;
        while let Some(byte) = self.bump()? {
            if prev == b'*' && byte == b'/' {
                return Ok(());
            }
            prev = byte;
        }
        Err(ParseError::new(line, column, "unterminated block comment"))
    }

    fn bump(&mut self) -> Result<Option<u8>, ParseError> {
        self.fill_peek(1)?;
        let Some(byte) = self.peeked.pop_front() else {
            return Ok(None);
        };
        if byte == b'\n' {
            self.line += 1;
            self.column = 1;
        } else {
            self.column += 1;
        }
        Ok(Some(byte))
    }

    fn peek(&mut self) -> Result<Option<u8>, ParseError> {
        self.fill_peek(1)?;
        Ok(self.peeked.front().copied())
    }

    fn peek_next(&mut self) -> Result<Option<u8>, ParseError> {
        self.fill_peek(2)?;
        Ok(self.peeked.get(1).copied())
    }

    fn fill_peek(&mut self, len: usize) -> Result<(), ParseError> {
        while !self.eof && self.peeked.len() < len {
            let mut byte = [0_u8; 1];
            match self.reader.read(&mut byte)? {
                0 => self.eof = true,
                _ => self.peeked.push_back(byte[0]),
            }
        }
        Ok(())
    }
}

#[derive(Default)]
struct LibraryUnits {
    voltage: Option<String>,
    current: Option<String>,
    time: Option<String>,
    capacitive_load: Option<String>,
    templates: Vec<(String, [Option<String>; 3])>,
    attributes: Vec<(String, String)>,
    driver_waveforms: Vec<TimingTableData>,
}

struct Parser {
    lexer: Lexer,
    current: Option<Token>,
    cell_filter: Option<HashSet<String>>,
}

impl Parser {
    fn new(
        reader: Box<dyn Read>,
        cell_filter: Option<HashSet<String>>,
    ) -> Result<Self, ParseError> {
        let mut parser = Self {
            lexer: Lexer::new(reader)?,
            current: None,
            cell_filter,
        };
        parser.advance()?;
        Ok(parser)
    }

    fn parse_document(&mut self) -> Result<Document, ParseError> {
        let mut library_name = String::new();
        let mut cells = Vec::new();
        let mut bus_types = Vec::new();
        let mut units = LibraryUnits::default();

        while self.current.is_some() {
            // A '}' here has no matching open group at top level: the file has
            // unbalanced braces (e.g. the ASAP7 SIMPLE group ships a spurious
            // '}' that closes `library` early). Report it instead of failing
            // later with a cryptic "expected identifier" at the next token.
            if let Some(Token {
                kind: TokenKind::Symbol(b'}'),
                line,
                column,
            }) = self.current
            {
                return Err(ParseError::new(
                    line,
                    column,
                    "unexpected '}': unbalanced braces (a group has an extra \
                     closing brace, or an opening brace is missing earlier)",
                ));
            }
            let name_pos = self.current_position();
            let name = self.take_word()?;
            let args = if self.consume_symbol(b'(')? {
                self.read_args(&name)?
            } else {
                Vec::new()
            };
            self.expect_symbol(b'{')?;
            if name == "library" {
                library_name = args.first().cloned().unwrap_or_default();
                self.parse_library_body(&mut cells, &mut bus_types, &mut units)?;
            } else {
                // The only valid top-level group is `library`. Anything else
                // here (commonly a `cell` left orphaned by a premature library
                // close) signals unbalanced braces.
                let (line, column) = name_pos;
                return Err(ParseError::new(
                    line,
                    column,
                    &format!(
                        "unexpected top-level {name:?} group: expected a single \
                         'library' group (unbalanced braces may have closed it early)"
                    ),
                ));
            }
            self.consume_symbol(b';')?;
        }

        if library_name.is_empty() {
            return Err(self.error_here("missing top-level library group"));
        }

        Ok(Document {
            library_name,
            voltage_unit: units.voltage,
            current_unit: units.current,
            time_unit: units.time,
            capacitive_load_unit: units.capacitive_load,
            templates: units.templates,
            attributes: units.attributes,
            driver_waveforms: units.driver_waveforms,
            cells,
            bus_types,
        })
    }

    fn parse_library_body(
        &mut self,
        cells: &mut Vec<CellData>,
        bus_types: &mut Vec<BusTypeData>,
        units: &mut LibraryUnits,
    ) -> Result<(), ParseError> {
        while !self.consume_symbol(b'}')? {
            let name = self.take_word()?;
            if self.consume_symbol(b'(')? {
                let args = self.read_args(&name)?;
                if self.consume_symbol(b'{')? {
                    match name.as_str() {
                        "cell" => {
                            let cell_name = args.first().cloned().unwrap_or_default();
                            if self
                                .cell_filter
                                .as_ref()
                                .map_or(true, |filter| filter.contains(&cell_name))
                            {
                                cells.push(self.parse_cell_body(cell_name)?);
                            } else {
                                self.skip_group_body()?;
                            }
                        }
                        "type" => {
                            bus_types.push(
                                self.parse_bus_type_body(
                                    args.first().cloned().unwrap_or_default(),
                                )?,
                            );
                        }
                        "lu_table_template" | "power_lut_template" | "output_current_template" => {
                            let tmpl_name = args.first().cloned().unwrap_or_default();
                            let vars = self.parse_template_body()?;
                            units.templates.push((tmpl_name, vars));
                        }
                        "normalized_driver_waveform" => {
                            let tmpl = args.first().cloned();
                            units
                                .driver_waveforms
                                .push(self.parse_timing_table_body(String::new(), tmpl)?);
                        }
                        _ => {
                            self.skip_group_body()?;
                        }
                    }
                    self.consume_symbol(b';')?;
                } else {
                    // Complex attribute, e.g. `capacitive_load_unit (1, ff)`.
                    if name == "capacitive_load_unit" {
                        units.capacitive_load = args.get(1).cloned();
                    }
                    units.attributes.push((name, args.join(", ")));
                    self.consume_symbol(b';')?;
                }
            } else if self.consume_symbol(b':')? {
                let value = self.read_simple_attribute_value()?;
                match name.as_str() {
                    "voltage_unit" => units.voltage = Some(value.clone()),
                    "current_unit" => units.current = Some(value.clone()),
                    "time_unit" => units.time = Some(value.clone()),
                    _ => {}
                }
                units.attributes.push((name, value));
            } else {
                return Err(self.error_here("expected '(' or ':' after library item name"));
            }
        }
        Ok(())
    }

    fn parse_cell_body(&mut self, name: String) -> Result<CellData, ParseError> {
        let mut area = None;
        let mut pins = Vec::new();
        let mut buses = Vec::new();
        let mut bundles = Vec::new();
        let mut attributes = Vec::new();
        let mut dynamic_currents = Vec::new();
        while !self.consume_symbol(b'}')? {
            let item_name = self.take_word()?;
            if self.consume_symbol(b'(')? {
                let args = self.read_args(&item_name)?;
                if self.consume_symbol(b'{')? {
                    match item_name.as_str() {
                        "pin" => {
                            pins.push(
                                self.parse_pin_body(args.first().cloned().unwrap_or_default())?,
                            );
                        }
                        "bus" => {
                            buses.push(
                                self.parse_bus_body(args.first().cloned().unwrap_or_default())?,
                            );
                        }
                        "bundle" => {
                            bundles.push(
                                self.parse_bundle_body(args.first().cloned().unwrap_or_default())?,
                            );
                        }
                        "dynamic_current" => {
                            dynamic_currents.push(self.parse_dynamic_current_body()?);
                        }
                        _ => {
                            self.skip_group_body()?;
                        }
                    }
                    self.consume_symbol(b';')?;
                } else {
                    attributes.push((item_name, args.join(", ")));
                    self.consume_symbol(b';')?;
                }
            } else if self.consume_symbol(b':')? {
                let value = self.read_simple_attribute_value()?;
                if item_name == "area" {
                    area = parse_number(&value);
                }
                attributes.push((item_name, value));
            } else {
                return Err(self.error_here("expected '(' or ':' after cell item name"));
            }
        }
        Ok(CellData {
            name,
            area,
            pins,
            buses,
            bundles,
            attributes,
            dynamic_currents,
        })
    }

    fn parse_dynamic_current_body(&mut self) -> Result<DynamicCurrentData, ParseError> {
        let mut related_inputs = None;
        let mut related_outputs = None;
        let mut when = None;
        let mut switching_groups = Vec::new();
        while !self.consume_symbol(b'}')? {
            let item_name = self.take_word()?;
            if self.consume_symbol(b'(')? {
                let _args = self.read_args(&item_name)?;
                if self.consume_symbol(b'{')? {
                    if item_name == "switching_group" {
                        switching_groups.push(self.parse_switching_group_body()?);
                    } else {
                        self.skip_group_body()?;
                    }
                    self.consume_symbol(b';')?;
                } else {
                    // Complex attr (e.g. typical_capacitances) — ignored.
                    self.consume_symbol(b';')?;
                }
            } else if self.consume_symbol(b':')? {
                let value = self.read_simple_attribute_value()?;
                match item_name.as_str() {
                    "related_inputs" => related_inputs = Some(value),
                    "related_outputs" => related_outputs = Some(value),
                    "when" => when = Some(value),
                    _ => {}
                }
            } else {
                return Err(self.error_here("expected '(' or ':' in dynamic_current"));
            }
        }
        Ok(DynamicCurrentData {
            related_inputs,
            related_outputs,
            when,
            switching_groups,
        })
    }

    fn parse_switching_group_body(&mut self) -> Result<SwitchingGroupData, ParseError> {
        let mut input_switching_condition = None;
        let mut output_switching_condition = None;
        let mut pg_currents = Vec::new();
        while !self.consume_symbol(b'}')? {
            let item_name = self.take_word()?;
            if self.consume_symbol(b'(')? {
                let args = self.read_args(&item_name)?;
                if self.consume_symbol(b'{')? {
                    if item_name == "pg_current" {
                        pg_currents.push(self.parse_pg_current_body(args.first().cloned())?);
                    } else {
                        self.skip_group_body()?;
                    }
                    self.consume_symbol(b';')?;
                } else {
                    // `input_switching_condition (rise)` etc. are complex attrs.
                    match item_name.as_str() {
                        "input_switching_condition" => {
                            input_switching_condition = args.first().cloned();
                        }
                        "output_switching_condition" => {
                            output_switching_condition = args.first().cloned();
                        }
                        _ => {}
                    }
                    self.consume_symbol(b';')?;
                }
            } else if self.consume_symbol(b':')? {
                let _ = self.read_simple_attribute_value()?;
            } else {
                return Err(self.error_here("expected '(' or ':' in switching_group"));
            }
        }
        Ok(SwitchingGroupData {
            input_switching_condition,
            output_switching_condition,
            pg_currents,
        })
    }

    fn parse_pg_current_body(
        &mut self,
        pg_pin: Option<String>,
    ) -> Result<PgCurrentData, ParseError> {
        let mut vectors = Vec::new();
        while !self.consume_symbol(b'}')? {
            let item_name = self.take_word()?;
            if self.consume_symbol(b'(')? {
                let args = self.read_args(&item_name)?;
                if self.consume_symbol(b'{')? {
                    if item_name == "vector" {
                        let tmpl = args.first().cloned();
                        vectors.push(self.parse_timing_table_body("vector".to_string(), tmpl)?);
                    } else {
                        self.skip_group_body()?;
                    }
                    self.consume_symbol(b';')?;
                } else {
                    self.consume_symbol(b';')?;
                }
            } else if self.consume_symbol(b':')? {
                let _ = self.read_simple_attribute_value()?;
            } else {
                return Err(self.error_here("expected '(' or ':' in pg_current"));
            }
        }
        Ok(PgCurrentData { pg_pin, vectors })
    }

    fn parse_pin_body(&mut self, name: String) -> Result<PinData, ParseError> {
        let mut direction = None;
        let mut function = None;
        let mut timing_arcs = Vec::new();
        let mut internal_powers = Vec::new();
        let mut attributes = Vec::new();
        while !self.consume_symbol(b'}')? {
            let item_name = self.take_word()?;
            if self.consume_symbol(b'(')? {
                let args = self.read_args(&item_name)?;
                if self.consume_symbol(b'{')? {
                    match item_name.as_str() {
                        "timing" => timing_arcs.push(self.parse_timing_body()?),
                        "internal_power" => internal_powers.push(self.parse_internal_power_body()?),
                        _ => self.skip_group_body()?,
                    }
                    self.consume_symbol(b';')?;
                } else {
                    // Complex attribute, e.g. `rise_capacitance_range (0.55, 0.74)`.
                    attributes.push((item_name, args.join(", ")));
                    self.consume_symbol(b';')?;
                }
            } else if self.consume_symbol(b':')? {
                let value = self.read_simple_attribute_value()?;
                match item_name.as_str() {
                    "direction" => direction = Some(value.clone()),
                    "function" => function = Some(value.clone()),
                    _ => {}
                }
                attributes.push((item_name, value));
            } else {
                return Err(self.error_here("expected '(' or ':' after pin item name"));
            }
        }
        Ok(PinData {
            name,
            direction,
            function,
            timing_arcs,
            internal_powers,
            attributes,
        })
    }

    fn parse_internal_power_body(&mut self) -> Result<InternalPowerData, ParseError> {
        let mut related_pin = None;
        let mut related_pg_pin = None;
        let mut when = None;
        let mut tables = Vec::new();
        while !self.consume_symbol(b'}')? {
            let item_name = self.take_word()?;
            if self.consume_symbol(b'(')? {
                let args = self.read_args(&item_name)?;
                if self.consume_symbol(b'{')? {
                    if is_power_table_group(&item_name) {
                        let template = args.first().cloned();
                        tables.push(self.parse_timing_table_body(item_name, template)?);
                    } else {
                        self.skip_group_body()?;
                    }
                    self.consume_symbol(b';')?;
                } else {
                    self.consume_symbol(b';')?;
                }
            } else if self.consume_symbol(b':')? {
                let value = self.read_simple_attribute_value()?;
                match item_name.as_str() {
                    "related_pin" => related_pin = Some(value),
                    "related_pg_pin" => related_pg_pin = Some(value),
                    "when" => when = Some(value),
                    _ => {}
                }
            } else {
                return Err(self.error_here("expected '(' or ':' after internal_power item name"));
            }
        }
        Ok(InternalPowerData {
            related_pin,
            related_pg_pin,
            when,
            tables,
        })
    }

    fn parse_bus_body(&mut self, name: String) -> Result<BusData, ParseError> {
        let mut direction = None;
        let mut function = None;
        let mut bus_type = None;
        let mut pins = Vec::new();
        let mut timing_arcs = Vec::new();
        while !self.consume_symbol(b'}')? {
            let item_name = self.take_word()?;
            if self.consume_symbol(b'(')? {
                let args = self.read_args(&item_name)?;
                if self.consume_symbol(b'{')? {
                    match item_name.as_str() {
                        "pin" => {
                            pins.push(
                                self.parse_pin_body(args.first().cloned().unwrap_or_default())?,
                            );
                        }
                        "timing" => {
                            timing_arcs.push(self.parse_timing_body()?);
                        }
                        _ => {
                            self.skip_group_body()?;
                        }
                    }
                    self.consume_symbol(b';')?;
                } else {
                    if item_name == "members" {
                        pins.extend(members_from_args(&args).into_iter().map(|name| PinData {
                            name,
                            direction: direction.clone(),
                            function: None,
                            timing_arcs: Vec::new(),
                            internal_powers: Vec::new(),
                            attributes: Vec::new(),
                        }));
                    }
                    self.consume_symbol(b';')?;
                }
            } else if self.consume_symbol(b':')? {
                let value = self.read_simple_attribute_value()?;
                match item_name.as_str() {
                    "direction" => direction = Some(value),
                    "function" => function = Some(value),
                    "bus_type" => bus_type = Some(value),
                    _ => {}
                }
            } else {
                return Err(self.error_here("expected '(' or ':' after bus item name"));
            }
        }
        Ok(BusData {
            name,
            direction,
            function,
            bus_type,
            pins,
            timing_arcs,
        })
    }

    fn parse_bundle_body(&mut self, name: String) -> Result<BundleData, ParseError> {
        let mut direction = None;
        let mut function = None;
        let mut members = Vec::new();
        let mut pins = Vec::new();
        let mut timing_arcs = Vec::new();
        while !self.consume_symbol(b'}')? {
            let item_name = self.take_word()?;
            if self.consume_symbol(b'(')? {
                let args = self.read_args(&item_name)?;
                if self.consume_symbol(b'{')? {
                    match item_name.as_str() {
                        "pin" => {
                            pins.push(
                                self.parse_pin_body(args.first().cloned().unwrap_or_default())?,
                            );
                        }
                        "timing" => {
                            timing_arcs.push(self.parse_timing_body()?);
                        }
                        _ => {
                            self.skip_group_body()?;
                        }
                    }
                    self.consume_symbol(b';')?;
                } else {
                    if item_name == "members" {
                        members = members_from_args(&args);
                    }
                    self.consume_symbol(b';')?;
                }
            } else if self.consume_symbol(b':')? {
                let value = self.read_simple_attribute_value()?;
                match item_name.as_str() {
                    "direction" => direction = Some(value),
                    "function" => function = Some(value),
                    _ => {}
                }
            } else {
                return Err(self.error_here("expected '(' or ':' after bundle item name"));
            }
        }
        Ok(BundleData {
            name,
            direction,
            function,
            members,
            pins,
            timing_arcs,
        })
    }

    fn parse_bus_type_body(&mut self, name: String) -> Result<BusTypeData, ParseError> {
        let mut attributes = Vec::new();
        while !self.consume_symbol(b'}')? {
            let item_name = self.take_word()?;
            if self.consume_symbol(b':')? {
                attributes.push((item_name, self.read_simple_attribute_value()?));
            } else if self.consume_symbol(b'(')? {
                let _args = self.read_args(&item_name)?;
                if self.consume_symbol(b'{')? {
                    self.skip_group_body()?;
                } else {
                    self.consume_symbol(b';')?;
                }
            } else {
                return Err(self.error_here("expected '(' or ':' after type item name"));
            }
        }
        Ok(BusTypeData { name, attributes })
    }

    /// Read `variable_1/2/3` from a lookup-table template group, skipping the
    /// index rows. Returns the three axis variable names (any may be None).
    fn parse_template_body(&mut self) -> Result<[Option<String>; 3], ParseError> {
        let mut vars: [Option<String>; 3] = [None, None, None];
        while !self.consume_symbol(b'}')? {
            let item_name = self.take_word()?;
            if self.consume_symbol(b'(')? {
                let _args = self.read_args(&item_name)?;
                if self.consume_symbol(b'{')? {
                    self.skip_group_body()?;
                }
                self.consume_symbol(b';')?;
            } else if self.consume_symbol(b':')? {
                let value = self.read_simple_attribute_value()?;
                match item_name.as_str() {
                    "variable_1" => vars[0] = Some(value),
                    "variable_2" => vars[1] = Some(value),
                    "variable_3" => vars[2] = Some(value),
                    _ => {}
                }
            } else {
                return Err(self.error_here("expected '(' or ':' in template body"));
            }
        }
        Ok(vars)
    }

    fn parse_timing_body(&mut self) -> Result<TimingArcData, ParseError> {
        let mut related_pin = None;
        let mut timing_type = None;
        let mut when = None;
        let mut tables = Vec::new();
        while !self.consume_symbol(b'}')? {
            let item_name = self.take_word()?;
            if self.consume_symbol(b'(')? {
                let args = self.read_args(&item_name)?;
                if self.consume_symbol(b'{')? {
                    if is_timing_table_group(&item_name) {
                        let template = args.first().cloned();
                        tables.push(self.parse_timing_table_body(item_name, template)?);
                    } else {
                        self.skip_group_body()?;
                    }
                    self.consume_symbol(b';')?;
                } else {
                    self.consume_symbol(b';')?;
                }
            } else if self.consume_symbol(b':')? {
                let value = self.read_simple_attribute_value()?;
                match item_name.as_str() {
                    "related_pin" => related_pin = Some(value),
                    "timing_type" => timing_type = Some(value),
                    "when" => when = Some(value),
                    _ => {}
                }
            } else {
                return Err(self.error_here("expected '(' or ':' after timing item name"));
            }
        }
        Ok(TimingArcData {
            related_pin,
            timing_type,
            when,
            tables,
        })
    }

    fn parse_timing_table_body(
        &mut self,
        mut name: String,
        template: Option<String>,
    ) -> Result<TimingTableData, ParseError> {
        let mut index_1 = Vec::new();
        let mut index_2 = Vec::new();
        let mut index_3 = Vec::new();
        let mut values = Vec::new();
        let mut reference_time = None;
        let mut vectors = Vec::new();
        while !self.consume_symbol(b'}')? {
            let item_name = self.take_word()?;
            if self.consume_symbol(b'(')? {
                let args = self.read_args(&item_name)?;
                if self.consume_symbol(b'{')? {
                    // A nested group: CCS `output_current_*` / `ccsn_*` tables
                    // contain `vector` sub-groups, each a current-vs-time wave.
                    if item_name == "vector" {
                        let vtemplate = args.first().cloned();
                        vectors.push(self.parse_timing_table_body(item_name, vtemplate)?);
                    } else {
                        self.skip_group_body()?;
                    }
                    self.consume_symbol(b';')?;
                } else {
                    self.consume_symbol(b';')?;
                    match item_name.as_str() {
                        "index_1" => index_1 = parse_float_list(args.first()),
                        "index_2" => index_2 = parse_float_list(args.first()),
                        "index_3" => index_3 = parse_float_list(args.first()),
                        "values" => values = parse_float_args(&args),
                        _ => {}
                    }
                }
            } else if self.consume_symbol(b':')? {
                let value = self.read_simple_attribute_value()?;
                if item_name == "reference_time" {
                    reference_time = parse_number(&value);
                } else if item_name == "driver_waveform_name" {
                    // normalized_driver_waveform groups name themselves here, not
                    // in the group header (which holds the template name).
                    name = value;
                }
            } else {
                return Err(self.error_here("expected '(' or ':' after table item name"));
            }
        }
        Ok(TimingTableData {
            name,
            index_1,
            index_2,
            index_3,
            values,
            template,
            reference_time,
            vectors,
        })
    }

    fn skip_group_body(&mut self) -> Result<(), ParseError> {
        let mut depth = 1usize;
        while let Some(token) = self.current.clone() {
            self.advance()?;
            match token.kind {
                TokenKind::Symbol(b'{') => depth += 1,
                TokenKind::Symbol(b'}') => {
                    depth -= 1;
                    if depth == 0 {
                        return Ok(());
                    }
                }
                _ => {}
            }
        }
        Err(self.error_here("unexpected end of file while skipping group"))
    }

    fn read_args(&mut self, name: &str) -> Result<Vec<String>, ParseError> {
        let mut args = Vec::new();
        let allow_spaces = matches!(
            name,
            "input_switching_condition" | "output_switching_condition"
        );
        while !self.consume_symbol(b')')? {
            args.push(self.read_value()?);
            if self.consume_symbol(b')')? {
                break;
            }
            if !allow_spaces {
                self.expect_symbol(b',')?;
            } else {
                self.consume_symbol(b',')?;
            }
        }
        Ok(args)
    }

    fn read_value(&mut self) -> Result<String, ParseError> {
        let mut value = self.take_word()?;
        if self.consume_symbol(b'[')? {
            let sel = self.take_word()?;
            self.expect_symbol(b']')?;
            value.push('[');
            value.push_str(&sel);
            value.push(']');
        }
        Ok(value)
    }

    fn read_simple_attribute_value(&mut self) -> Result<String, ParseError> {
        let mut parts = Vec::new();
        while !self.consume_symbol(b';')? {
            if self.current.is_none() {
                return Err(self.error_here("unexpected end of file in attribute value"));
            }
            parts.push(self.token_to_string()?);
            self.advance()?;
        }
        Ok(parts.join(" "))
    }

    fn take_word(&mut self) -> Result<String, ParseError> {
        match self.current.clone() {
            Some(Token {
                kind: TokenKind::Word(value),
                ..
            }) => {
                self.advance()?;
                Ok(value)
            }
            Some(token) => Err(ParseError::new(
                token.line,
                token.column,
                "expected identifier or value",
            )),
            None => Err(self.error_here("unexpected end of file")),
        }
    }

    fn token_to_string(&self) -> Result<String, ParseError> {
        match &self.current {
            Some(Token {
                kind: TokenKind::Word(value),
                ..
            }) => Ok(value.clone()),
            Some(Token {
                kind: TokenKind::Symbol(byte),
                ..
            }) => Ok((*byte as char).to_string()),
            None => Err(self.error_here("unexpected end of file")),
        }
    }

    fn consume_symbol(&mut self, symbol: u8) -> Result<bool, ParseError> {
        if matches!(
            self.current,
            Some(Token {
                kind: TokenKind::Symbol(current),
                ..
            }) if current == symbol
        ) {
            self.advance()?;
            Ok(true)
        } else {
            Ok(false)
        }
    }

    fn expect_symbol(&mut self, symbol: u8) -> Result<(), ParseError> {
        if self.consume_symbol(symbol)? {
            Ok(())
        } else {
            Err(self.error_here(&format!("expected '{}'", symbol as char)))
        }
    }

    fn advance(&mut self) -> Result<(), ParseError> {
        self.current = self.lexer.next_token()?;
        Ok(())
    }

    fn current_position(&self) -> (usize, usize) {
        match &self.current {
            Some(token) => (token.line, token.column),
            None => (self.lexer.line, self.lexer.column),
        }
    }

    fn error_here(&self, message: &str) -> ParseError {
        let (line, column) = self.current_position();
        ParseError::new(line, column, message)
    }
}

fn is_symbol(byte: u8) -> bool {
    matches!(
        byte,
        b',' | b'{' | b'}' | b'(' | b')' | b'[' | b']' | b';' | b':'
    )
}

fn is_timing_table_group(name: &str) -> bool {
    matches!(
        name,
        "cell_rise"
            | "cell_fall"
            | "rise_transition"
            | "fall_transition"
            | "rise_constraint"
            | "fall_constraint"
            | "cell_degradation"
            | "retaining_rise"
            | "retaining_fall"
            | "retain_rise_slew"
            | "retain_fall_slew"
            | "output_current_rise"
            | "output_current_fall"
            | "ccst_rise"
            | "ccst_fall"
            | "ccsp_rise"
            | "ccsp_fall"
            | "ccsn_first_stage"
            | "ccsn_last_stage"
            | "ccsn_rise_first_stage"
            | "ccsn_rise_last_stage"
            | "ccsn_fall_first_stage"
            | "ccsn_fall_last_stage"
            | "receiver_capacitance1_rise"
            | "receiver_capacitance1_fall"
            | "receiver_capacitance2_rise"
            | "receiver_capacitance2_fall"
    )
}

fn is_power_table_group(name: &str) -> bool {
    matches!(name, "rise_power" | "fall_power" | "power")
}

/// Parse a Liberty unit string (e.g. "1mA", "1ps", "1V") into its SI scale.
/// Returns magnitude * SI-prefix factor; "1mA" -> 1e-3, "1ps" -> 1e-12.
fn unit_scale(value: &str) -> Option<f64> {
    let value = value.trim();
    let split = value.find(|ch: char| ch.is_ascii_alphabetic())?;
    let (number, unit) = value.split_at(split);
    let magnitude: f64 = number.trim().parse().unwrap_or(1.0);
    // A multi-char unit (e.g. "mA", "ps") carries an SI prefix; "V"/"A"/"s" do not.
    let prefix_factor = if unit.len() >= 2 {
        match unit.chars().next()? {
            'f' => 1e-15,
            'p' => 1e-12,
            'n' => 1e-9,
            'u' => 1e-6,
            'm' => 1e-3,
            'k' => 1e3,
            'M' => 1e6,
            'G' => 1e9,
            _ => 1.0,
        }
    } else {
        1.0
    };
    Some(magnitude * prefix_factor)
}

fn parse_number(value: &str) -> Option<f64> {
    value.parse::<f64>().ok()
}

fn parse_float_list(value: Option<&String>) -> Vec<f64> {
    value
        .map(|items| {
            items
                .split(',')
                .filter_map(|item| item.trim().parse::<f64>().ok())
                .collect()
        })
        .unwrap_or_default()
}

fn parse_float_args(values: &[String]) -> Vec<f64> {
    values
        .iter()
        .flat_map(|items| items.split(','))
        .filter_map(|item| item.trim().parse::<f64>().ok())
        .collect()
}

fn members_from_args(args: &[String]) -> Vec<String> {
    args.iter()
        .flat_map(|arg| arg.split_whitespace())
        .map(str::trim)
        .filter(|item| !item.is_empty())
        .map(ToOwned::to_owned)
        .collect()
}

#[derive(Debug)]
struct ParseError {
    line: usize,
    column: usize,
    message: String,
}

impl ParseError {
    fn new(line: usize, column: usize, message: &str) -> Self {
        Self {
            line,
            column,
            message: message.to_string(),
        }
    }

    fn into_py(self) -> PyErr {
        PyValueError::new_err(format!(
            "Liberty parse error at line {}, column {}: {}",
            self.line, self.column, self.message
        ))
    }
}

impl From<io::Error> for ParseError {
    fn from(value: io::Error) -> Self {
        Self::new(0, 0, &value.to_string())
    }
}
