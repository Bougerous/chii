import sqlite3
import json
import re
from typing import List, Dict, Any, Tuple, Optional
import tkinter as tk
from tkinter import ttk, messagebox
import datetime


###############################################################################
# RangeParser Class
###############################################################################

class RangeParser:
    """Parses reference ranges from various textual formats into numeric low/high values and units."""

    def __init__(self):
        self.special_chars = {
            '³': '',
            '²': '',
            '⁻': '-',
            '⁺': '+',
            '₂': '2',
            '₃': '3'
        }
        self.unit_pattern = re.compile(r'[a-zA-Z/%]+.*$')
        self.number_pattern = re.compile(r'[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?')

    def parse_range(self, range_str: str) -> Tuple[Optional[float], Optional[float], str]:
        """Parse a given reference range string into (low, high, unit)."""
        if not isinstance(range_str, str) or not range_str.strip():
            return None, None, ''
        
        cleaned = self._clean_string(range_str)

        # Handle special cases (<, >)
        if '<' in cleaned:
            return self._handle_less_than(cleaned)
        if '>' in cleaned:
            return self._handle_greater_than(cleaned)

        numbers = self._extract_numbers(cleaned)
        unit = self._extract_unit(cleaned)
        return self._process_range(numbers, unit)

    def _clean_string(self, value: str) -> str:
        for char, replacement in self.special_chars.items():
            value = value.replace(char, replacement)
        # Normalize range separators
        value = value.replace(',', '').replace('–', '-').replace(' to ', '-')
        value = value.replace('−', '-').replace('—', '-')
        return value.strip()

    def _extract_numbers(self, value: str) -> list:
        return [float(n) for n in self.number_pattern.findall(value)]

    def _extract_unit(self, value: str) -> str:
        match = self.unit_pattern.search(value)
        return match.group().strip() if match else ''

    def _process_range(self, numbers: list, unit: str) -> Tuple[Optional[float], Optional[float], str]:
        if len(numbers) >= 2:
            return numbers[0], numbers[1], unit
        elif len(numbers) == 1:
            return numbers[0], numbers[0], unit
        return None, None, unit

    def _handle_less_than(self, value: str) -> Tuple[Optional[float], Optional[float], str]:
        numbers = self._extract_numbers(value)
        unit = self._extract_unit(value)
        return (None, numbers[0], unit) if numbers else (None, None, unit)

    def _handle_greater_than(self, value: str) -> Tuple[Optional[float], Optional[float], str]:
        numbers = self._extract_numbers(value)
        unit = self._extract_unit(value)
        return (numbers[0], None, unit) if numbers else (None, None, unit)


###############################################################################
# LabDatabase Class
###############################################################################

class LabDatabase:
    """Handles all SQLite database interactions for lab parameters."""

    def __init__(self, db_name: str = "lab_parameters.db"):
        self.db_name = db_name
        self.conn = sqlite3.connect(db_name)
        self.parser = RangeParser()
        self.create_tables()

    def create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS lab_parameters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parameter_name TEXT NOT NULL,
            category TEXT,
            sub_category TEXT,
            age_group TEXT NOT NULL,
            low_range REAL NOT NULL,
            high_range REAL NOT NULL,
            unit TEXT,
            notes TEXT,
            UNIQUE(parameter_name, age_group)
        )
        ''')
        self.conn.commit()

    def add_parameter(self, parameter_name: str, category: str, sub_category: str, 
                      age_group: str, low_range: float, high_range: float, 
                      unit: str = None, notes: str = None) -> bool:
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO lab_parameters 
                (parameter_name, category, sub_category, age_group, low_range, high_range, unit, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (parameter_name, category, sub_category, age_group, low_range, high_range, unit, notes))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def get_parameter(self, parameter_name: str, age_group: str = None) -> list:
        cursor = self.conn.cursor()
        if age_group:
            cursor.execute('''
            SELECT * FROM lab_parameters 
            WHERE parameter_name LIKE ? AND age_group = ?
            ''', (f'%{parameter_name}%', age_group))
        else:
            cursor.execute('''
            SELECT * FROM lab_parameters 
            WHERE parameter_name LIKE ?
            ''', (f'%{parameter_name}%',))
        return cursor.fetchall()

    def list_all_parameters(self) -> list:
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM lab_parameters')
        return cursor.fetchall()

    def update_parameter(self, old_param_name: str, old_age_group: str,
                         new_param_name: str, new_category: str, new_sub_category: str, new_age_group: str,
                         low_range: float, high_range: float,
                         unit: str = None, notes: str = None) -> bool:
        try:
            cursor = self.conn.cursor()
            # Check uniqueness if changing param name or age group
            if (old_param_name != new_param_name or old_age_group != new_age_group):
                cursor.execute('''
                SELECT COUNT(*) FROM lab_parameters 
                WHERE parameter_name=? AND age_group=? 
                  AND (parameter_name!=? OR age_group!=?)
                ''', (new_param_name, new_age_group, old_param_name, old_age_group))
                if cursor.fetchone()[0] > 0:
                    return False

            cursor.execute('''
            UPDATE lab_parameters 
            SET parameter_name=?, category=?, sub_category=?, age_group=?, low_range=?, high_range=?, unit=?, notes=?
            WHERE parameter_name=? AND age_group=?
            ''', (new_param_name, new_category, new_sub_category, new_age_group, low_range, high_range, unit, notes,
                  old_param_name, old_age_group))
            self.conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error:
            return False

    def remove_parameter(self, parameter_name: str, age_group: str) -> bool:
        try:
            cursor = self.conn.cursor()
            cursor.execute('DELETE FROM lab_parameters WHERE parameter_name=? AND age_group=?',
                           (parameter_name, age_group))
            self.conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error:
            return False

    def close(self):
        self.conn.close()

    def __del__(self):
        self.close()

    def get_unique_units(self):
        cursor = self.conn.cursor()
        cursor.execute('SELECT DISTINCT unit FROM lab_parameters WHERE unit IS NOT NULL')
        return [row[0] for row in cursor.fetchall()]

    def add_parameters_from_json(self, json_data: Dict[str, Any]) -> None:
        """Parses a JSON structure and inserts the parameters into the DB."""
        cursor = self.conn.cursor()
        for category, tests in json_data.get("NICU_Tests", {}).items():
            # If tests is a dict of subcategories:
            if isinstance(tests, dict) and any(isinstance(v, list) for v in tests.values()):
                # AdvancedTests like structure: category -> subcategory -> tests[]
                for sub_cat, sub_tests in tests.items():
                    for test in sub_tests:
                        self._process_and_insert_test(cursor, test, category, sub_cat)
            else:
                # Normal: category -> tests[]
                for test in tests:
                    self._process_and_insert_test(cursor, test, category, None)
        self.conn.commit()

    def _process_and_insert_test(self, cursor, test, category, sub_category):
        try:
            parameter_name = test["Test"]
            reference_range = test["ReferenceRange"]

            if isinstance(reference_range, dict):
                for age_group, range_value in reference_range.items():
                    low, high, unit = self.parser.parse_range(str(range_value))
                    if low is not None and high is not None:
                        self._insert_parameter(cursor, parameter_name, category, sub_category, age_group, low, high, unit)
            else:
                low, high, unit = self.parser.parse_range(str(reference_range))
                if low is not None and high is not None:
                    self._insert_parameter(cursor, parameter_name, category, sub_category, "All", low, high, unit)
        except Exception as e:
            print(f"Error processing {test.get('Test', 'Unknown')}: {str(e)}")

    def _insert_parameter(self, cursor, name, category, sub_category, age_group, low, high, unit):
        cursor.execute('''
            INSERT OR IGNORE INTO lab_parameters 
            (parameter_name, category, sub_category, age_group, low_range, high_range, unit, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (name, category, sub_category, age_group, low, high, unit, ''))


###############################################################################
# EditParameterDialog Class
###############################################################################

class EditParameterDialog(tk.Toplevel):
    def __init__(self, parent, values, age_groups, units):
        super().__init__(parent.root)
        self.title("Edit Parameter")
        self.parent = parent
        self.result = None

        # values = (Parameter, Category, Age Group, Range, Unit, Notes)
        param_name, category, age_group, param_range, unit, notes = values
        low_val, high_val = [v.strip() for v in param_range.split("-")]

        tk.Label(self, text="Parameter Name:").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        self.param_name_entry = ttk.Entry(self)
        self.param_name_entry.insert(0, param_name)
        self.param_name_entry.grid(row=0, column=1, padx=5, pady=5)

        tk.Label(self, text="Category:").grid(row=1, column=0, padx=5, pady=5, sticky="e")
        self.category_entry = ttk.Entry(self)
        self.category_entry.insert(0, category)
        self.category_entry.grid(row=1, column=1, padx=5, pady=5)

        tk.Label(self, text="Sub-Category:").grid(row=2, column=0, padx=5, pady=5, sticky="e")
        self.sub_category_entry = ttk.Entry(self)
        self.sub_category_entry.insert(0, "")
        self.sub_category_entry.grid(row=2, column=1, padx=5, pady=5)

        tk.Label(self, text="Age Group:").grid(row=3, column=0, padx=5, pady=5, sticky="e")
        self.age_group_combo = ttk.Combobox(self, values=age_groups, state="readonly")
        self.age_group_combo.set(age_group)
        self.age_group_combo.grid(row=3, column=1, padx=5, pady=5)

        tk.Label(self, text="Lower Range:").grid(row=4, column=0, padx=5, pady=5, sticky="e")
        self.low_range_entry = ttk.Entry(self)
        self.low_range_entry.insert(0, low_val)
        self.low_range_entry.grid(row=4, column=1, padx=5, pady=5)

        tk.Label(self, text="Higher Range:").grid(row=5, column=0, padx=5, pady=5, sticky="e")
        self.high_range_entry = ttk.Entry(self)
        self.high_range_entry.insert(0, high_val)
        self.high_range_entry.grid(row=5, column=1, padx=5, pady=5)

        tk.Label(self, text="Unit:").grid(row=6, column=0, padx=5, pady=5, sticky="e")
        self.unit_combo = ttk.Combobox(self, values=units, state="readonly")
        if unit:
            self.unit_combo.set(unit)
        self.unit_combo.grid(row=6, column=1, padx=5, pady=5)

        tk.Label(self, text="Notes:").grid(row=7, column=0, padx=5, pady=5, sticky="e")
        self.notes_entry = ttk.Entry(self)
        if notes:
            self.notes_entry.insert(0, notes)
        self.notes_entry.grid(row=7, column=1, padx=5, pady=5)

        button_frame = tk.Frame(self)
        button_frame.grid(row=8, column=0, columnspan=2, pady=10)

        ok_button = ttk.Button(button_frame, text="OK", command=self.on_ok)
        ok_button.grid(row=0, column=0, padx=5)

        cancel_button = ttk.Button(button_frame, text="Cancel", command=self.on_cancel)
        cancel_button.grid(row=0, column=1, padx=5)

    def on_ok(self):
        param_name = self.param_name_entry.get().strip()
        category = self.category_entry.get().strip() if self.category_entry.get().strip() else None
        sub_category = self.sub_category_entry.get().strip() if self.sub_category_entry.get().strip() else None
        age_group = self.age_group_combo.get().strip()
        low_val = self.low_range_entry.get().strip()
        high_val = self.high_range_entry.get().strip()
        unit = self.unit_combo.get().strip() if self.unit_combo.get() else None
        notes = self.notes_entry.get().strip() if self.notes_entry.get() else None

        if not param_name:
            messagebox.showerror("Error", "Parameter Name cannot be empty.", parent=self)
            return
        if not age_group:
            messagebox.showerror("Error", "Age Group cannot be empty.", parent=self)
            return
        try:
            low = float(low_val)
            high = float(high_val)
        except ValueError:
            messagebox.showerror("Error", "Please enter valid numbers for ranges!", parent=self)
            return
        if low >= high:
            messagebox.showerror("Error", "Lower range must be less than higher range.", parent=self)
            return

        self.result = (param_name, category, sub_category, age_group, low, high, unit, notes)
        self.destroy()

    def on_cancel(self):
        self.result = None
        self.destroy()


###############################################################################
# LabParametersGUI Class
###############################################################################

class LabParametersGUI:
    AGE_GROUPS = [
        "Neonate",
        "Infant",
        "Child",
        "Adolescent",
        "Adult",
        "Pregnancy",
        "Term",
        "Preterm",
        "All"
    ]

    UNITS = [
        "g/dL", "mg/dL", "µg/dL",
        "mmol/L", "µmol/L",
        "mEq/L", "ng/mL",
        "U/L", "IU/L",
        "%",
        "cells/µL",
        "g/L",
        "pg",
        "ratio",
        "seconds",
        "K/µL",
        "mm/hr",
        "mm³",
        "mmHg",
        "µIU/mL",
        "ng/dL",
        "pg/mL",
        "cells/mm³",
        "mg/L",
        "/mm³",
        "pg/dL"
    ]

    # Static categories based on provided database categories
    CATEGORIES = [
        "Hematology",
        "BloodGas",
        "Electrolytes",
        "LiverFunctionTests",
        "RenalFunctionTests",
        "InfectionMarkers",
        "Coagulation",
        "Other"
    ]

    # Static subcategories (no subcategories used, just empty)
    SUBCATEGORIES = {
        "Hematology": [],
        "BloodGas": [],
        "Electrolytes": [],
        "LiverFunctionTests": [],
        "RenalFunctionTests": [],
        "InfectionMarkers": [],
        "Coagulation": [],
        "Other": []
    }

    def __init__(self, root):
        self.root = root
        self.db = LabDatabase()
        self.root.title("Lab Parameters Database")
        self.root.geometry("1000x700")

        # Apply a theme for better aesthetics
        style = ttk.Style()
        style.theme_use("clam")

        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        self.notebook = ttk.Notebook(self.root)
        self.notebook.grid(row=0, column=0, sticky="nsew", padx=10, pady=5)

        self.add_tab = ttk.Frame(self.notebook)
        self.search_tab = ttk.Frame(self.notebook)
        self.view_tab = ttk.Frame(self.notebook)
        self.parse_tab = ttk.Frame(self.notebook)

        self.notebook.add(self.add_tab, text="Add Parameter")
        self.notebook.add(self.search_tab, text="Search")
        self.notebook.add(self.view_tab, text="View All")
        self.notebook.add(self.parse_tab, text="Parse Text Input")

        self.setup_add_tab()
        self.setup_search_tab()
        self.setup_view_tab()
        self.setup_parse_tab()

        # Set static categories and subcategories
        self.category['values'] = self.CATEGORIES
        self.category.set("")
        self.sub_category['values'] = []
        self.sub_category.set("")

        units_from_db = self.db.get_unique_units()
        all_units = sorted(list(set(self.UNITS + units_from_db)))
        self.unit['values'] = all_units

    def setup_add_tab(self):
        for i in range(7):
            self.add_tab.grid_columnconfigure(1, weight=1)

        ttk.Label(self.add_tab, text="Parameter Name:").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        self.param_name = ttk.Entry(self.add_tab)
        self.param_name.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        ttk.Label(self.add_tab, text="Category:").grid(row=1, column=0, padx=5, pady=5, sticky="e")
        self.category = ttk.Combobox(self.add_tab, state="readonly")
        self.category.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        ttk.Label(self.add_tab, text="Sub-Category:").grid(row=2, column=0, padx=5, pady=5, sticky="e")
        self.sub_category = ttk.Combobox(self.add_tab, state="readonly")
        self.sub_category.grid(row=2, column=1, padx=5, pady=5, sticky="ew")

        ttk.Label(self.add_tab, text="Age Group:").grid(row=3, column=0, padx=5, pady=5, sticky="e")
        self.age_group = ttk.Combobox(self.add_tab, values=self.AGE_GROUPS, state="readonly")
        self.age_group.grid(row=3, column=1, padx=5, pady=5, sticky="ew")

        ttk.Label(self.add_tab, text="Lower Range:").grid(row=4, column=0, padx=5, pady=5, sticky="e")
        self.low_range = ttk.Entry(self.add_tab)
        self.low_range.grid(row=4, column=1, padx=5, pady=5, sticky="ew")

        ttk.Label(self.add_tab, text="Higher Range:").grid(row=5, column=0, padx=5, pady=5, sticky="e")
        self.high_range = ttk.Entry(self.add_tab)
        self.high_range.grid(row=5, column=1, padx=5, pady=5, sticky="ew")

        ttk.Label(self.add_tab, text="Unit:").grid(row=6, column=0, padx=5, pady=5, sticky="e")
        self.unit = ttk.Combobox(self.add_tab, state="readonly")
        self.unit.grid(row=6, column=1, padx=5, pady=5, sticky="ew")

        ttk.Label(self.add_tab, text="Notes:").grid(row=7, column=0, padx=5, pady=5, sticky="e")
        self.notes = ttk.Entry(self.add_tab)
        self.notes.grid(row=7, column=1, padx=5, pady=5, sticky="ew")

        ttk.Button(self.add_tab, text="Add Parameter", command=self.add_parameter).grid(row=8, column=0, columnspan=2, pady=20)

    def setup_search_tab(self):
        self.search_tab.grid_columnconfigure(1, weight=1)

        search_frame = ttk.Frame(self.search_tab)
        search_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)

        ttk.Label(search_frame, text="Parameter Name:").grid(row=0, column=0, padx=5, pady=5)
        self.search_name = ttk.Entry(search_frame)
        self.search_name.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(search_frame, text="Age Group (optional):").grid(row=1, column=0, padx=5, pady=5)
        self.search_age = ttk.Combobox(search_frame, values=[""] + self.AGE_GROUPS, state="readonly")
        self.search_age.grid(row=1, column=1, padx=5, pady=5)

        button_frame = ttk.Frame(self.search_tab)
        button_frame.grid(row=1, column=0, pady=5)

        ttk.Button(button_frame, text="Search", command=self.search_parameters).grid(row=0, column=0, padx=5)
        ttk.Button(button_frame, text="Edit Selected", command=lambda: self.edit_selected(self.search_tree)).grid(row=0, column=1, padx=5)
        ttk.Button(button_frame, text="Delete Selected", command=lambda: self.remove_selected(self.search_tree)).grid(row=0, column=2, padx=5)

        self.search_tree = ttk.Treeview(self.search_tab, columns=("Parameter", "Category", "Age Group", "Range", "Unit", "Notes"), show="headings")
        self.setup_treeview(self.search_tree)
        self.search_tree.grid(row=2, column=0, sticky="nsew", padx=5, pady=5)

        scrollbar = ttk.Scrollbar(self.search_tab, orient="vertical", command=self.search_tree.yview)
        scrollbar.grid(row=2, column=1, sticky="ns")
        self.search_tree.configure(yscrollcommand=scrollbar.set)

    def setup_view_tab(self):
        self.view_tab.grid_rowconfigure(1, weight=1)
        self.view_tab.grid_columnconfigure(0, weight=1)

        button_frame = ttk.Frame(self.view_tab)
        button_frame.grid(row=0, column=0, pady=5)

        ttk.Button(button_frame, text="Refresh", command=self.refresh_view).grid(row=0, column=0, padx=5)
        ttk.Button(button_frame, text="Edit Selected", command=lambda: self.edit_selected(self.view_tree)).grid(row=0, column=1, padx=5)
        ttk.Button(button_frame, text="Delete Selected", command=lambda: self.remove_selected(self.view_tree)).grid(row=0, column=2, padx=5)
        ttk.Button(button_frame, text="Export Database", command=self.export_database).grid(row=0, column=3, padx=5)

        style = ttk.Style()
        style.configure("Danger.TButton", foreground="red")
        ttk.Button(button_frame, text="Purge Database", command=self.purge_database, style="Danger.TButton").grid(row=0, column=4, padx=5)

        self.view_tree = ttk.Treeview(self.view_tab, columns=("Parameter", "Category", "Age Group", "Range", "Unit", "Notes"), show="headings")
        self.setup_treeview(self.view_tree)
        self.view_tree.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)

        scrollbar = ttk.Scrollbar(self.view_tab, orient="vertical", command=self.view_tree.yview)
        scrollbar.grid(row=1, column=1, sticky="ns")
        self.view_tree.configure(yscrollcommand=scrollbar.set)

        self.refresh_view()

    def setup_parse_tab(self):
        self.parse_tab.grid_rowconfigure(1, weight=1)
        self.parse_tab.grid_columnconfigure(0, weight=1)

        parse_frame = ttk.Frame(self.parse_tab)
        parse_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        ttk.Label(parse_frame, text="Paste your unstructured text (JSON) below:").grid(row=0, column=0, sticky="w", pady=5)

        self.raw_text = tk.Text(parse_frame, wrap="word", height=10)
        self.raw_text.grid(row=1, column=0, sticky="nsew", pady=5, padx=5)

        btn_frame = ttk.Frame(parse_frame)
        btn_frame.grid(row=2, column=0, sticky="ew", pady=5)
        ttk.Button(btn_frame, text="Parse", command=self.parse_text_input).grid(row=0, column=0, padx=5)
        ttk.Button(btn_frame, text="Clear All", command=lambda: self.raw_text.delete("1.0", tk.END)).grid(row=0, column=1, padx=5)

        self.parsed_tree = ttk.Treeview(self.parse_tab, columns=("Parameter", "Age Group", "Range", "Unit", "Notes"), show="headings")
        self.setup_treeview(self.parsed_tree)
        self.parsed_tree.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)

        parse_confirm_frame = ttk.Frame(self.parse_tab)
        parse_confirm_frame.grid(row=2, column=0, sticky="ew", pady=5)

        ttk.Button(parse_confirm_frame, text="Select All", command=lambda: self.select_all_items(self.parsed_tree)).grid(row=0, column=0, padx=5)
        ttk.Button(parse_confirm_frame, text="Confirm Selected", command=self.confirm_parsed_selected).grid(row=0, column=1, padx=5)

    def setup_treeview(self, tree):
        columns = tree["columns"]
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=100)

    def add_parameter(self):
        param_name = self.param_name.get().strip()
        category = self.category.get().strip() if self.category.get().strip() else None
        sub_category = self.sub_category.get().strip() if self.sub_category.get().strip() else None
        age_grp = self.age_group.get().strip()
        low_val = self.low_range.get().strip()
        high_val = self.high_range.get().strip()

        if not param_name:
            messagebox.showerror("Error", "Parameter Name cannot be empty.")
            return
        if not age_grp:
            messagebox.showerror("Error", "Age Group cannot be empty.")
            return
        if not category:
            messagebox.showerror("Error", "Category cannot be empty.")
            return

        try:
            low = float(low_val)
            high = float(high_val)
        except ValueError:
            messagebox.showerror("Error", "Please enter valid numbers for ranges!")
            return

        if low >= high:
            messagebox.showerror("Error", "Lower range must be less than higher range.")
            return

        success = self.db.add_parameter(
            param_name,
            category,
            sub_category,
            age_grp,
            low,
            high,
            self.unit.get().strip() if self.unit.get() else None,
            self.notes.get().strip() if self.notes.get() else None
        )

        if success:
            messagebox.showinfo("Success", "Parameter added successfully!")
            for field in [self.param_name, self.low_range, self.high_range, self.notes]:
                field.delete(0, tk.END)
            self.category.set("")
            self.sub_category.set("")
            self.age_group.set("")
            self.unit.set("")
        else:
            messagebox.showerror("Error", "Parameter for this age group already exists!")

    def search_parameters(self):
        for item in self.search_tree.get_children():
            self.search_tree.delete(item)

        param_name = self.search_name.get().strip()
        age_grp = self.search_age.get().strip() if self.search_age.get().strip() else None

        if not param_name:
            messagebox.showerror("Error", "Please enter a parameter name to search.")
            return

        results = self.db.get_parameter(param_name, age_grp)
        for result in results:
            self.search_tree.insert("", "end", values=(
                result[1],
                result[2] if result[2] else "",
                result[4],
                f"{result[5]} - {result[6]}",
                result[7] if result[7] else "",
                result[8] if result[8] else ""
            ))

    def refresh_view(self):
        for item in self.view_tree.get_children():
            self.view_tree.delete(item)

        results = self.db.list_all_parameters()
        for result in results:
            self.view_tree.insert("", "end", values=(
                result[1],  # Parameter
                result[2] if result[2] else "",  # Category
                result[4],  # Age Group
                f"{result[5]} - {result[6]}",  # Range
                result[7] if result[7] else "", # Unit
                result[8] if result[8] else ""  # Notes
            ))

    def edit_selected(self, tree):
        selected_items = tree.selection()
        if not selected_items:
            messagebox.showwarning("Warning", "Please select a parameter to edit")
            return

        selected_item = selected_items[0]
        values = tree.item(selected_item)['values']
        if values:
            dialog = EditParameterDialog(self, values, self.AGE_GROUPS, self.UNITS)
            self.root.wait_window(dialog)
            if dialog.result:
                (param_name, category, sub_category, age_group, low, high, unit, notes) = dialog.result
                old_param_name = values[0]
                old_age_group = values[2]
                updated = self.db.update_parameter(old_param_name, old_age_group, param_name, category, sub_category, age_group, low, high, unit, notes)
                if updated:
                    tree.item(selected_item, values=(
                        param_name,
                        category if category else "",
                        age_group,
                        f"{low} - {high}",
                        unit if unit else "",
                        notes if notes else ""
                    ))
                    messagebox.showinfo("Success", "Parameter updated successfully!")
                    if tree == self.search_tree:
                        self.search_parameters()
                    if tree == self.view_tree:
                        self.refresh_view()
                else:
                    messagebox.showerror("Error", "Failed to update parameter!")

    def remove_selected(self, tree):
        selected_items = tree.selection()
        if not selected_items:
            messagebox.showwarning("Warning", "Please select a parameter to delete")
            return

        selected_item = selected_items[0]
        values = tree.item(selected_item)['values']
        if values:
            param_name = values[0]
            age_group = values[2]
            if messagebox.askyesno("Confirm", f"Remove parameter {param_name} for age group {age_group}?"):
                if self.db.remove_parameter(param_name, age_group):
                    tree.delete(selected_item)
                    messagebox.showinfo("Success", "Parameter removed successfully!")
                    if tree == self.search_tree:
                        self.search_parameters()
                    if tree == self.view_tree:
                        self.refresh_view()
                else:
                    messagebox.showerror("Error", "Failed to remove parameter!")

    def parse_text_input(self):
        for item in self.parsed_tree.get_children():
            self.parsed_tree.delete(item)

        raw_data = self.raw_text.get("1.0", tk.END).strip()
        if not raw_data:
            messagebox.showerror("Error", "No JSON data provided for parsing.")
            return

        try:
            parsed_entries = self.parse_nicu_reference_ranges(raw_data)

            if not parsed_entries:
                messagebox.showwarning("No Matches", "No parameter entries found. Please check your input JSON.")
                return

            for entry in parsed_entries:
                # entry: (test_name, category, sub_category, age_group, low, high, unit, '')
                test_name, category, sub_category, age_group, low, high, unit, notes = entry
                range_str = f"{low} - {high}"
                notes_str = notes if notes else (f"Category: {category}" if category else "")
                self.parsed_tree.insert("", "end", values=(
                    test_name,
                    age_group,
                    range_str,
                    unit if unit else "",
                    notes_str
                ))

        except json.JSONDecodeError as e:
            messagebox.showerror("JSON Error", f"Invalid JSON format: {str(e)}")
        except Exception as e:
            messagebox.showerror("Error", f"Error processing data: {str(e)}")

    def confirm_parsed_selected(self):
        selected_items = self.parsed_tree.selection()
        if not selected_items:
            messagebox.showwarning("Warning", "Please select parameters to confirm")
            return

        success_messages = []
        error_messages = []

        for sel in selected_items:
            values = self.parsed_tree.item(sel)['values']
            # values: (param_name, age, range, unit, notes)
            param_name = values[0]
            age = values[1]
            rng = values[2]
            unit = values[3]
            notes = values[4]

            try:
                low_val, high_val = [v.strip() for v in rng.split("-")]
                low = float(low_val)
                high = float(high_val)
            except ValueError:
                error_messages.append(f"Invalid numeric range for {param_name}")
                continue

            if low >= high:
                error_messages.append(f"Lower range must be less than higher range for {param_name}")
                continue

            success = self.db.add_parameter(
                param_name,
                None,
                None,
                age,
                low,
                high,
                unit if unit else None,
                notes if notes else None
            )

            if success:
                success_messages.append(f"Parameter '{param_name}' added successfully!")
            else:
                error_messages.append(f"Parameter '{param_name}' for age group '{age}' already exists!")

        summary = ""
        if success_messages:
            summary += "Successfully added:\n" + "\n".join(success_messages) + "\n\n"
        if error_messages:
            summary += "Errors:\n" + "\n".join(error_messages)

        if summary:
            messagebox.showinfo("Import Summary", summary)

    def parse_nicu_reference_ranges(self, json_data):
        if isinstance(json_data, str):
            data = json.loads(json_data)
        else:
            data = json_data

        if not isinstance(data, dict) or 'NICU_Tests' not in data:
            raise ValueError("Invalid JSON structure: Expected 'NICU_Tests' as top-level key")

        results = []
        parser = self.db.parser

        def process_test(test_data, category, sub_category=None):
            if not isinstance(test_data, dict) or 'Test' not in test_data or 'ReferenceRange' not in test_data:
                return

            test_name = test_data['Test']
            ref_range = test_data['ReferenceRange']

            if isinstance(ref_range, dict):
                for age_group, range_str in ref_range.items():
                    low, high, unit = parser.parse_range(str(range_str))
                    if low is not None and high is not None:
                        results.append((test_name, category, sub_category, age_group, low, high, unit, ''))
            else:
                low, high, unit = parser.parse_range(str(ref_range))
                if low is not None and high is not None:
                    # Default to 'All' if no age group specified
                    results.append((test_name, category, sub_category, 'All', low, high, unit, ''))

        for category, tests in data['NICU_Tests'].items():
            # If this is a nested category structure:
            if isinstance(tests, dict) and any(isinstance(v, list) for v in tests.values()):
                for sub_cat, sub_tests in tests.items():
                    for test in sub_tests:
                        process_test(test, category, sub_cat)
            else:
                for test in tests:
                    process_test(test, category, None)

        return results

    def select_all_items(self, tree):
        tree.selection_remove(tree.selection())
        for item in tree.get_children():
            tree.selection_add(item)

    def export_database(self):
        try:
            cursor = self.db.conn.cursor()
            cursor.execute('SELECT * FROM lab_parameters')
            rows = cursor.fetchall()

            output = "Database Content:\n\n"
            for row in rows:
                output += (
                    f"ID: {row[0]}\n"
                    f"Parameter: {row[1]}\n"
                    f"Category: {row[2]}\n"
                    f"Sub-Category: {row[3]}\n"
                    f"Age Group: {row[4]}\n"
                    f"Range: {row[5]} - {row[6]}\n"
                    f"Unit: {row[7]}\n"
                    f"Notes: {row[8]}\n"
                    + "-" * 50 + "\n"
                )

            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"database_export_{timestamp}.txt"

            with open(filename, 'w', encoding='utf-8') as f:
                f.write(output)

            messagebox.showinfo("Success", f"Database exported successfully to {filename}")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to export database: {str(e)}")

    def purge_database(self):
        if messagebox.askyesno("Confirm Purge",
                               "Are you sure you want to purge the entire database?\n\n"
                               "This action cannot be undone!",
                               icon='warning'):
            try:
                self.export_database()
                cursor = self.db.conn.cursor()
                cursor.execute('DELETE FROM lab_parameters')
                self.db.conn.commit()
                self.refresh_view()
                messagebox.showinfo("Success", "Database has been purged successfully.\nA backup was created before purging.")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to purge database: {str(e)}")


###############################################################################
# Main Function
###############################################################################

def main():
    root = tk.Tk()
    app = LabParametersGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
