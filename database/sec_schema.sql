--
-- PostgreSQL database dump
--

\restrict eMJhWeqPu3tOsEhKXegDfnWeuOJn9rlE6RurE5OcUQUoB99xBjOJwywDpmakpxq

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
    project_count integer DEFAULT 0,
    source text DEFAULT 'unknown'::text,
    former_id integer,
    has_flood boolean DEFAULT false,
    has_dime boolean DEFAULT false,
    has_philgeps boolean DEFAULT false
);


ALTER TABLE public.contractors OWNER TO budget_admin;

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
-- Name: contractors id; Type: DEFAULT; Schema: public; Owner: budget_admin
--

ALTER TABLE ONLY public.contractors ALTER COLUMN id SET DEFAULT nextval('public.contractors_id_seq'::regclass);


--
-- Name: contractors contractors_pkey; Type: CONSTRAINT; Schema: public; Owner: budget_admin
--

ALTER TABLE ONLY public.contractors
    ADD CONSTRAINT contractors_pkey PRIMARY KEY (id);


--
-- Name: contractors_sec_number_unique; Type: INDEX; Schema: public; Owner: budget_admin
--

CREATE UNIQUE INDEX contractors_sec_number_unique ON public.contractors USING btree (sec_number) WHERE (sec_number IS NOT NULL);


--
-- Name: contractors contractors_former_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: budget_admin
--

ALTER TABLE ONLY public.contractors
    ADD CONSTRAINT contractors_former_id_fkey FOREIGN KEY (former_id) REFERENCES public.contractors(id);


--
-- PostgreSQL database dump complete
--

\unrestrict eMJhWeqPu3tOsEhKXegDfnWeuOJn9rlE6RurE5OcUQUoB99xBjOJwywDpmakpxq

