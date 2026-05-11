use flate2::read::GzDecoder;
use pyo3::exceptions::{PyKeyError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use std::collections::{HashSet, VecDeque};
use std::fs::File;
use std::io::{self, BufReader, Read};

#[pyclass]
#[derive(Clone)]
struct Document {
    #[pyo3(get)]
    library_name: String,
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
    values: Vec<f64>,
}

#[derive(Clone)]
struct CellData {
    name: String,
    area: Option<f64>,
    pins: Vec<PinData>,
    buses: Vec<BusData>,
    bundles: Vec<BundleData>,
}

#[derive(Clone)]
struct PinData {
    name: String,
    direction: Option<String>,
    function: Option<String>,
    timing_arcs: Vec<TimingArcData>,
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
    values: Vec<f64>,
}

impl From<CellData> for Cell {
    fn from(value: CellData) -> Self {
        Self {
            name: value.name,
            area: value.area,
            pins: value.pins,
            buses: value.buses,
            bundles: value.bundles,
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
            values: value.values,
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
                values: self.values.clone(),
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
    m.add_function(wrap_pyfunction!(parse_file, m)?)?;
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
    let cols = table_cols(table);
    for (idx, value) in table.values.iter().enumerate() {
        let row = PyDict::new(py);
        row.set_item("cell", cell)?;
        row.set_item("pin", pin)?;
        row.set_item("related_pin", arc.related_pin.as_deref())?;
        row.set_item("timing_type", arc.timing_type.as_deref())?;
        row.set_item("when", arc.when.as_deref())?;
        row.set_item("table", &table.name)?;
        let i = if cols == 0 { idx } else { idx / cols };
        let j = if cols == 0 { 0 } else { idx % cols };
        row.set_item("index_1", table.index_1.get(i).copied())?;
        row.set_item("index_2", table.index_2.get(j).copied())?;
        row.set_item("row", i)?;
        row.set_item("col", j)?;
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

fn table_cols(table: &TimingTableData) -> usize {
    if !table.index_2.is_empty() {
        table.index_2.len()
    } else if !table.index_1.is_empty() {
        table.index_1.len()
    } else {
        table.values.len()
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

        while self.current.is_some() {
            let name = self.take_word()?;
            let args = if self.consume_symbol(b'(')? {
                self.read_args(&name)?
            } else {
                Vec::new()
            };
            self.expect_symbol(b'{')?;
            if name == "library" {
                library_name = args.first().cloned().unwrap_or_default();
                self.parse_library_body(&mut cells, &mut bus_types)?;
            } else {
                self.skip_group_body()?;
            }
            self.consume_symbol(b';')?;
        }

        if library_name.is_empty() {
            return Err(self.error_here("missing top-level library group"));
        }

        Ok(Document {
            library_name,
            cells,
            bus_types,
        })
    }

    fn parse_library_body(
        &mut self,
        cells: &mut Vec<CellData>,
        bus_types: &mut Vec<BusTypeData>,
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
                        _ => {
                            self.skip_group_body()?;
                        }
                    }
                    self.consume_symbol(b';')?;
                } else {
                    self.consume_symbol(b';')?;
                }
            } else if self.consume_symbol(b':')? {
                self.skip_attribute_value()?;
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
                        _ => {
                            self.skip_group_body()?;
                        }
                    }
                    self.consume_symbol(b';')?;
                } else {
                    self.consume_symbol(b';')?;
                }
            } else if self.consume_symbol(b':')? {
                let value = self.read_simple_attribute_value()?;
                if item_name == "area" {
                    area = parse_number(&value);
                }
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
        })
    }

    fn parse_pin_body(&mut self, name: String) -> Result<PinData, ParseError> {
        let mut direction = None;
        let mut function = None;
        let mut timing_arcs = Vec::new();
        while !self.consume_symbol(b'}')? {
            let item_name = self.take_word()?;
            if self.consume_symbol(b'(')? {
                let _args = self.read_args(&item_name)?;
                if self.consume_symbol(b'{')? {
                    if item_name == "timing" {
                        timing_arcs.push(self.parse_timing_body()?);
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
                    "direction" => direction = Some(value),
                    "function" => function = Some(value),
                    _ => {}
                }
            } else {
                return Err(self.error_here("expected '(' or ':' after pin item name"));
            }
        }
        Ok(PinData {
            name,
            direction,
            function,
            timing_arcs,
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

    fn parse_timing_body(&mut self) -> Result<TimingArcData, ParseError> {
        let mut related_pin = None;
        let mut timing_type = None;
        let mut when = None;
        let mut tables = Vec::new();
        while !self.consume_symbol(b'}')? {
            let item_name = self.take_word()?;
            if self.consume_symbol(b'(')? {
                let _args = self.read_args(&item_name)?;
                if self.consume_symbol(b'{')? {
                    if is_timing_table_group(&item_name) {
                        tables.push(self.parse_timing_table_body(item_name)?);
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

    fn parse_timing_table_body(&mut self, name: String) -> Result<TimingTableData, ParseError> {
        let mut index_1 = Vec::new();
        let mut index_2 = Vec::new();
        let mut values = Vec::new();
        while !self.consume_symbol(b'}')? {
            let item_name = self.take_word()?;
            if self.consume_symbol(b'(')? {
                let args = self.read_args(&item_name)?;
                self.consume_symbol(b';')?;
                match item_name.as_str() {
                    "index_1" => index_1 = parse_float_list(args.first()),
                    "index_2" => index_2 = parse_float_list(args.first()),
                    "values" => values = parse_float_args(&args),
                    _ => {}
                }
            } else if self.consume_symbol(b':')? {
                self.skip_attribute_value()?;
            } else {
                return Err(self.error_here("expected '(' or ':' after table item name"));
            }
        }
        Ok(TimingTableData {
            name,
            index_1,
            index_2,
            values,
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

    fn skip_attribute_value(&mut self) -> Result<(), ParseError> {
        while !self.consume_symbol(b';')? {
            if self.current.is_none() {
                return Err(self.error_here("unexpected end of file in attribute value"));
            }
            self.advance()?;
        }
        Ok(())
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

    fn error_here(&self, message: &str) -> ParseError {
        if let Some(token) = &self.current {
            ParseError::new(token.line, token.column, message)
        } else {
            ParseError::new(self.lexer.line, self.lexer.column, message)
        }
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
            | "receiver_capacitance1_rise"
            | "receiver_capacitance1_fall"
            | "receiver_capacitance2_rise"
            | "receiver_capacitance2_fall"
    )
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
