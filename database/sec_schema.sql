--
-- PostgreSQL database dump
--

\restrict ZW4woyU15JkHGQPjCuMsW1V4dQQfh6cs6JLRS8faLY52bzy7beqyr2qvafUZrdS

-- Dumped from database version 14.19 (Ubuntu 14.19-0ubuntu0.22.04.1)
-- Dumped by pg_dump version 14.19 (Ubuntu 14.19-0ubuntu0.22.04.1)

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
-- Name: contractors; Type: TABLE; Schema: public; Owner: budget_admin
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
    project_count integer DEFAULT 0
);


ALTER TABLE public.contractors OWNER TO budget_admin;

--
-- Name: project_contractors; Type: TABLE; Schema: public; Owner: budget_admin
--

CREATE TABLE public.project_contractors (
    id integer NOT NULL,
    project_id text NOT NULL,
    contractor_name text NOT NULL,
    contractor_role character varying(50),
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.project_contractors OWNER TO budget_admin;

--
-- Name: contractors_id_seq; Type: SEQUENCE; Schema: public; Owner: budget_admin
--

CREATE SEQUENCE public.contractors_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.contractors_id_seq OWNER TO budget_admin;

--
-- Name: contractors_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: budget_admin
--

ALTER SEQUENCE public.contractors_id_seq OWNED BY public.contractors.id;


--
-- Name: project_contractors_id_seq; Type: SEQUENCE; Schema: public; Owner: budget_admin
--

CREATE SEQUENCE public.project_contractors_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.project_contractors_id_seq OWNER TO budget_admin;

--
-- Name: project_contractors_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: budget_admin
--

ALTER SEQUENCE public.project_contractors_id_seq OWNED BY public.project_contractors.id;


--
-- Name: contractors id; Type: DEFAULT; Schema: public; Owner: budget_admin
--

ALTER TABLE ONLY public.contractors ALTER COLUMN id SET DEFAULT nextval('public.contractors_id_seq'::regclass);


--
-- Name: project_contractors id; Type: DEFAULT; Schema: public; Owner: budget_admin
--

ALTER TABLE ONLY public.project_contractors ALTER COLUMN id SET DEFAULT nextval('public.project_contractors_id_seq'::regclass);


--
-- Name: contractors contractors_pkey; Type: CONSTRAINT; Schema: public; Owner: budget_admin
--

ALTER TABLE ONLY public.contractors
    ADD CONSTRAINT contractors_pkey PRIMARY KEY (id);


--
-- Name: project_contractors project_contractors_pkey; Type: CONSTRAINT; Schema: public; Owner: budget_admin
--

ALTER TABLE ONLY public.project_contractors
    ADD CONSTRAINT project_contractors_pkey PRIMARY KEY (id);


--
-- Name: project_contractors project_contractors_project_id_contractor_name_contractor_r_key; Type: CONSTRAINT; Schema: public; Owner: budget_admin
--

ALTER TABLE ONLY public.project_contractors
    ADD CONSTRAINT project_contractors_project_id_contractor_name_contractor_r_key UNIQUE (project_id, contractor_name, contractor_role);


--
-- Name: contractors_sec_number_unique; Type: INDEX; Schema: public; Owner: budget_admin
--

CREATE UNIQUE INDEX contractors_sec_number_unique ON public.contractors USING btree (sec_number) WHERE (sec_number IS NOT NULL);


--
-- Name: idx_contractors_name; Type: INDEX; Schema: public; Owner: budget_admin
--

CREATE INDEX idx_contractors_name ON public.contractors USING btree (contractor_name);


--
-- Name: idx_contractors_sec_number; Type: INDEX; Schema: public; Owner: budget_admin
--

CREATE INDEX idx_contractors_sec_number ON public.contractors USING btree (sec_number);


--
-- Name: idx_project_contractors_contractor; Type: INDEX; Schema: public; Owner: budget_admin
--

CREATE INDEX idx_project_contractors_contractor ON public.project_contractors USING btree (contractor_name);


--
-- Name: idx_project_contractors_project_id; Type: INDEX; Schema: public; Owner: budget_admin
--

CREATE INDEX idx_project_contractors_project_id ON public.project_contractors USING btree (project_id);


--
-- PostgreSQL database dump complete
--

\unrestrict ZW4woyU15JkHGQPjCuMsW1V4dQQfh6cs6JLRS8faLY52bzy7beqyr2qvafUZrdS

