                                            Table "public.contractors"
       Column       |            Type             | Collation | Nullable |                 Default                 
--------------------+-----------------------------+-----------+----------+-----------------------------------------
 id                 | integer                     |           | not null | nextval('contractors_id_seq'::regclass)
 contractor_name    | text                        |           | not null | 
 sec_number         | character varying(255)      |           |          | 
 date_registered    | date                        |           |          | 
 status             | character varying(50)       |           |          | 
 address            | text                        |           |          | 
 secondary_licenses | text                        |           |          | 
 created_at         | timestamp without time zone |           |          | CURRENT_TIMESTAMP
 updated_at         | timestamp without time zone |           |          | CURRENT_TIMESTAMP
 project_count      | integer                     |           |          | 0
Indexes:
    "contractors_pkey" PRIMARY KEY, btree (id)
    "contractors_sec_number_unique" UNIQUE, btree (sec_number) WHERE sec_number IS NOT NULL
    "idx_contractors_name" btree (contractor_name)
    "idx_contractors_sec_number" btree (sec_number)

