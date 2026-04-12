import argparse
import os
from pathlib import Path

import networkx as nx
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()


def _safe_float(value, default=1.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _graphml_path(working_dir):
    return Path(working_dir) / "graph_chunk_entity_relation.graphml"


def _node_rows(graph):
    rows = []
    for node_id, attrs in graph.nodes(data=True):
        rows.append(
            {
                "id": str(node_id),
                "name": str(attrs.get("entity_id") or node_id),
                "display_name": str(attrs.get("entity_id") or node_id),
                "entity_type": str(attrs.get("entity_type", "unknown")),
                "description": str(attrs.get("description", "")),
                "source_id": str(attrs.get("source_id", "")),
                "file_path": str(attrs.get("file_path", "")),
                "created_at": str(attrs.get("created_at", "")),
            }
        )
    return rows


def _edge_rows(graph):
    rows = []
    for index, (source, target, attrs) in enumerate(graph.edges(data=True), start=1):
        rows.append(
            {
                "edge_id": f"{source}|{target}|{index}",
                "source": str(source),
                "target": str(target),
                "weight": _safe_float(attrs.get("weight"), 1.0),
                "description": str(attrs.get("description", "")),
                "keywords": str(attrs.get("keywords", "")),
                "source_id": str(attrs.get("source_id", "")),
                "file_path": str(attrs.get("file_path", "")),
                "created_at": str(attrs.get("created_at", "")),
            }
        )
    return rows


def _run_in_batches(session, query, rows, batch_size=500):
    for start in range(0, len(rows), batch_size):
        session.run(query, rows=rows[start : start + batch_size]).consume()


def import_graph_to_neo4j(
    working_dir,
    neo4j_uri=None,
    neo4j_username=None,
    neo4j_password=None,
    reset=False,
):
    graphml_path = _graphml_path(working_dir)
    if not graphml_path.exists():
        raise FileNotFoundError(f"GraphML file was not found: {graphml_path}")

    graph = nx.read_graphml(graphml_path)
    nodes = _node_rows(graph)
    edges = _edge_rows(graph)

    uri = neo4j_uri or os.getenv("NEO4J_URI")
    username = neo4j_username or os.getenv("NEO4J_USERNAME")
    password = neo4j_password or os.getenv("NEO4J_PASSWORD")

    if not uri or not username or not password:
        raise ValueError("NEO4J_URI, NEO4J_USERNAME, and NEO4J_PASSWORD are required.")

    create_constraint_query = """
    CREATE CONSTRAINT entity_id_unique IF NOT EXISTS
    FOR (e:Entity)
    REQUIRE e.id IS UNIQUE
    """

    reset_relationships_query = "MATCH ()-[r]->() DELETE r"
    reset_nodes_query = "MATCH (n) DELETE n"

    create_nodes_query = """
    UNWIND $rows AS row
    MERGE (e:Entity {id: row.id})
    SET e.name = row.name,
        e.displayName = row.display_name,
        e.entity_type = row.entity_type,
        e.description = row.description,
        e.source_id = row.source_id,
        e.file_path = row.file_path,
        e.created_at = row.created_at
    """

    create_edges_query = """
    UNWIND $rows AS row
    MATCH (source:Entity {id: row.source})
    MATCH (target:Entity {id: row.target})
    MERGE (source)-[rel:RELATED_TO {edge_id: row.edge_id}]->(target)
    SET rel.weight = row.weight,
        rel.description = row.description,
        rel.keywords = row.keywords,
        rel.source_id = row.source_id,
        rel.file_path = row.file_path,
        rel.created_at = row.created_at
    """

    driver = GraphDatabase.driver(uri, auth=(username, password))
    try:
        with driver.session() as session:
            session.run(create_constraint_query).consume()
            if reset:
                session.run(reset_relationships_query).consume()
                session.run(reset_nodes_query).consume()

            _run_in_batches(session, create_nodes_query, nodes)
            _run_in_batches(session, create_edges_query, edges)
    finally:
        driver.close()

    return {"nodes": len(nodes), "edges": len(edges), "graphml_path": str(graphml_path)}


def _build_parser():
    parser = argparse.ArgumentParser(description="Import GraphML into Neo4j.")
    parser.add_argument("working_dir", help="Directory that contains graph_chunk_entity_relation.graphml")
    parser.add_argument("--uri", dest="neo4j_uri", help="Neo4j bolt URI")
    parser.add_argument("--username", dest="neo4j_username", help="Neo4j username")
    parser.add_argument("--password", dest="neo4j_password", help="Neo4j password")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete existing nodes and relationships before import.",
    )
    return parser


if __name__ == "__main__":
    parser = _build_parser()
    args = parser.parse_args()
    result = import_graph_to_neo4j(
        working_dir=args.working_dir,
        neo4j_uri=args.neo4j_uri,
        neo4j_username=args.neo4j_username,
        neo4j_password=args.neo4j_password,
        reset=args.reset,
    )
    print(
        f"Imported {result['nodes']} nodes and {result['edges']} edges from {result['graphml_path']}"
    )
