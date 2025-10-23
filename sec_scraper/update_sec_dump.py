#!/usr/bin/env python3
"""
Update sec_dump.sql with latest SEC data from parsed results.
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Any

def load_parsed_results(file_path: str = "parsed_sec_results.json") -> Dict[str, Any]:
    """Load parsed SEC results from JSON file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def generate_sec_dump_sql(results: Dict[str, Any]) -> str:
    """
    Generate SQL dump content for SEC data.
    
    Args:
        results: Parsed SEC results dictionary
        
    Returns:
        SQL dump content as string
    """
    companies = results.get("companies", [])
    
    # Generate SQL header
    sql_content = f"""--
-- PostgreSQL database dump
--

-- Dumped from database version 14.19 (Ubuntu 14.19-0ubuntu0.22.04.1)
-- Dumped by pg_dump version 14.19 (Ubuntu 14.19-0ubuntu0.22.04.1)
-- Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
-- Total companies: {len(companies)}

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: contractors; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.contractors (
    id integer NOT NULL,
    contractor_name text NOT NULL,
    sec_number character varying(255),
    date_registered date,
    status character varying(50),
    address text,
    secondary_licenses text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    project_count integer DEFAULT 0,
    source text DEFAULT 'sec_scraper'::text,
    former_id integer,
    has_flood boolean DEFAULT false,
    has_dime boolean DEFAULT false,
    has_philgeps boolean DEFAULT false
);

--
-- Name: contractors_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.contractors_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER TABLE ONLY public.contractors ALTER COLUMN id SET DEFAULT nextval('public.contractors_id_seq'::regclass);

--
-- Data for Name: contractors; Type: TABLE DATA; Schema: public; Owner: -
--

"""
    
    # Add INSERT statements for each company
    for i, company in enumerate(companies, 1):
        # Escape single quotes in text fields
        company_name = company.get("company_name", "").replace("'", "''")
        sec_number = company.get("sec_number", "").replace("'", "''")
        date_registered = company.get("date_registered", "")
        status = company.get("status", "").replace("'", "''")
        address = company.get("address", "").replace("'", "''")
        secondary_licenses = str(company.get("secondary_licenses", [])).replace("'", "''")
        
        # Parse date if available
        parsed_date = "NULL"
        if date_registered:
            try:
                # Try to parse various date formats
                for fmt in ["%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%m/%d/%Y"]:
                    try:
                        parsed_date = f"'{datetime.strptime(date_registered, fmt).strftime('%Y-%m-%d')}'"
                        break
                    except ValueError:
                        continue
            except:
                parsed_date = "NULL"
        
        sql_content += f"""INSERT INTO public.contractors (id, contractor_name, sec_number, date_registered, status, address, secondary_licenses, source, created_at, updated_at) VALUES
({i}, '{company_name}', '{sec_number}', {parsed_date}, '{status}', '{address}', '{secondary_licenses}', 'sec_scraper', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

"""
    
    # Add sequence update and constraints
    sql_content += f"""
--
-- Name: contractors_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.contractors_id_seq OWNED BY public.contractors.id;

--
-- Name: contractors contractors_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contractors
    ADD CONSTRAINT contractors_pkey PRIMARY KEY (id);

--
-- Name: contractors_sec_number_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contractors
    ADD CONSTRAINT contractors_sec_number_key UNIQUE (sec_number);

--
-- PostgreSQL database dump complete
--
"""
    
    return sql_content

def update_sec_dump_file(sql_content: str, output_file: str = "../database/sec_dump.sql"):
    """
    Update the sec_dump.sql file with new content.
    
    Args:
        sql_content: SQL content to write
        output_file: Path to the sec_dump.sql file
    """
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(sql_content)
    
    print(f"Updated {output_file} with {len(sql_content.split('INSERT INTO')) - 1} companies")

def main():
    """Main function to update sec_dump.sql."""
    print("Loading parsed SEC results...")
    results = load_parsed_results()
    
    if not results:
        print("No parsed results found!")
        return
    
    companies = results.get("companies", [])
    print(f"Found {len(companies)} companies to add to sec_dump.sql")
    
    print("Generating SQL dump...")
    sql_content = generate_sec_dump_sql(results)
    
    print("Updating sec_dump.sql file...")
    update_sec_dump_file(sql_content)
    
    print("sec_dump.sql updated successfully!")

if __name__ == "__main__":
    main()
