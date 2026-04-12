import json
import os
import networkx as nx
import pandas as pd
from pyvis.network import Network
from graphrag.index.operations.cluster_graph import cluster_graph
from pathlib import Path


def create_simple_html(dataset):
  # Load the GraphML file
  filepath = f'./{dataset}/graph_chunk_entity_relation.graphml'
  G = nx.read_graphml(filepath)

  # Create a Pyvis network
  net = Network(notebook=True)

  # Convert NetworkX graph to Pyvis network
  net.from_nx(G)

  # Save and display the network
  net.show(f'./visualize/knowledge_graph_{dataset}_simple.html')

from yfiles_jupyter_graphs import GraphWidget
import streamlit as st

def show_hierarchy_graph(dataset):
  # クラスタリングの設定
  strategy = {
    "type": "leiden",
    "max_cluster_size": 10,  # クラスタの最大サイズ
    "use_lcc": True,         # 最大全結合成分のみを使用
    "seed": 0xDEADBEEF,      # ランダムシード
    "levels": None,          # すべてのレベルを使用
    "verbose": True          # ログを表示
  }

  # Load the GraphML file
  G = nx.read_graphml(f'./{dataset}/graph_chunk_entity_relation.graphml')

  # クラスタリングを実行
  communities = cluster_graph(G, strategy)

  # 結果を表示
  print("Detected communities:")
  base_communities = pd.DataFrame(
    communities, columns=pd.Index(["level", "community", "parent", "title"])
  ).explode("title")
  base_communities["community"] = base_communities["community"].astype(int)

  return base_communities

# load GraphML file and transfer to JSON
def graphml_to_json(graphml_file):
    G = nx.read_graphml(graphml_file)
    data = nx.node_link_data(G)
    return json.dumps(data)

# create HTML file
def save_as_html(html_path, graph_json):
    html_content = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Graph Visualization</title>
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <style>
        body, html {
            margin: 0;
            padding: 0;
            width: 100%;
            height: 100%;
            overflow: hidden;
        }
        svg {
            width: 100%;
            height: 100%;
        }
        .links line {
            stroke: #999;
            stroke-opacity: 0.6;
        }
        .nodes circle {
            stroke: #fff;
            stroke-width: 1.5px;
        }
        .node-label {
            font-size: 12px;
            pointer-events: none;
        }
        .link-label {
            font-size: 10px;
            fill: #666;
            pointer-events: none;
            opacity: 0;
            transition: opacity 0.3s;
        }
        .link:hover .link-label {
            opacity: 1;
        }
        .tooltip {
            position: absolute;
            text-align: left;
            padding: 10px;
            font: 12px sans-serif;
            background: lightsteelblue;
            border: 0px;
            border-radius: 8px;
            pointer-events: none;
            opacity: 0;
            transition: opacity 0.3s;
            max-width: 300px;
        }
        .legend {
            position: absolute;
            top: 10px;
            right: 10px;
            background-color: rgba(255, 255, 255, 0.8);
            padding: 10px;
            border-radius: 5px;
        }
        .legend-item {
            margin: 5px 0;
        }
        .legend-color {
            display: inline-block;
            width: 20px;
            height: 20px;
            margin-right: 5px;
            vertical-align: middle;
        }
    </style>
</head>
<body>
    <svg></svg>
    <div class="tooltip"></div>
    <div class="legend"></div>
    <script>
        [GRPH DATA];
        const graphData = graphJson;

        const svg = d3.select("svg"),
            width = window.innerWidth,
            height = window.innerHeight;

        svg.attr("viewBox", [0, 0, width, height]);

        const g = svg.append("g");

        const entityTypes = [...new Set(graphData.nodes.map(d => d.entity_type))];
        const color = d3.scaleOrdinal(d3.schemeCategory10).domain(entityTypes);

        const simulation = d3.forceSimulation(graphData.nodes)
            .force("link", d3.forceLink(graphData.links).id(d => d.id).distance(150))
            .force("charge", d3.forceManyBody().strength(-300))
            .force("center", d3.forceCenter(width / 2, height / 2))
            .force("collide", d3.forceCollide().radius(30));

        const linkGroup = g.append("g")
            .attr("class", "links")
            .selectAll("g")
            .data(graphData.links)
            .enter().append("g")
            .attr("class", "link");

        const link = linkGroup.append("line")
            .attr("stroke-width", d => Math.sqrt(d.value));

        const linkLabel = linkGroup.append("text")
            .attr("class", "link-label")
            .text(d => d.description || "");

        const node = g.append("g")
            .attr("class", "nodes")
            .selectAll("circle")
            .data(graphData.nodes)
            .enter().append("circle")
            .attr("r", 5)
            .attr("fill", d => color(d.entity_type))
            .call(d3.drag()
                .on("start", dragstarted)
                .on("drag", dragged)
                .on("end", dragended));

        const nodeLabel = g.append("g")
            .attr("class", "node-labels")
            .selectAll("text")
            .data(graphData.nodes)
            .enter().append("text")
            .attr("class", "node-label")
            .text(d => d.id);

        const tooltip = d3.select(".tooltip");

        node.on("mouseover", function(event, d) {
            tooltip.transition()
                .duration(200)
                .style("opacity", .9);
            tooltip.html(`<strong>${d.id}</strong><br>Entity Type: ${d.entity_type}<br>Description: ${d.description || "N/A"}`)
                .style("left", (event.pageX + 10) + "px")
                .style("top", (event.pageY - 28) + "px");
        })
        .on("mouseout", function(d) {
            tooltip.transition()
                .duration(500)
                .style("opacity", 0);
        });

        const legend = d3.select(".legend");
        entityTypes.forEach(type => {
            legend.append("div")
                .attr("class", "legend-item")
                .html(`<span class="legend-color" style="background-color: ${color(type)}"></span>${type}`);
        });

        simulation
            .nodes(graphData.nodes)
            .on("tick", ticked);

        simulation.force("link")
            .links(graphData.links);

        function ticked() {
            link
                .attr("x1", d => d.source.x)
                .attr("y1", d => d.source.y)
                .attr("x2", d => d.target.x)
                .attr("y2", d => d.target.y);

            linkLabel
                .attr("x", d => (d.source.x + d.target.x) / 2)
                .attr("y", d => (d.source.y + d.target.y) / 2)
                .attr("text-anchor", "middle")
                .attr("dominant-baseline", "middle");

            node
                .attr("cx", d => d.x)
                .attr("cy", d => d.y);

            nodeLabel
                .attr("x", d => d.x + 8)
                .attr("y", d => d.y + 3);
        }

        function dragstarted(event) {
            if (!event.active) simulation.alphaTarget(0.3).restart();
            event.subject.fx = event.subject.x;
            event.subject.fy = event.subject.y;
        }

        function dragged(event) {
            event.subject.fx = event.x;
            event.subject.fy = event.y;
        }

        function dragended(event) {
            if (!event.active) simulation.alphaTarget(0);
            event.subject.fx = null;
            event.subject.fy = null;
        }

        const zoom = d3.zoom()
            .scaleExtent([0.1, 10])
            .on("zoom", zoomed);

        svg.call(zoom);

        function zoomed(event) {
            g.attr("transform", event.transform);
        }

    </script>
</body>
</html>
    '''

    html_content = html_content.replace("[GRPH DATA]", graph_json)

    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

def create_json(json_data):
    json_data = "var graphJson = " + json_data.replace('\\"', '').replace("'", "\\'").replace("\n", "")

    return json_data

# main function
def visualize_graphml(dataset, html_path):
    graphml_file = f'./{dataset}/graph_chunk_entity_relation.graphml'
    json_data = graphml_to_json(graphml_file)
    html_dir = os.path.dirname(html_path)
    if not os.path.exists(html_dir):
        os.makedirs(html_dir)

    save_as_html(html_path, create_json(json_data))


def _get_graphml_path(dataset):
    return Path(dataset) / "graph_chunk_entity_relation.graphml"


def _load_graph(dataset):
    graphml_path = _get_graphml_path(dataset)
    if not graphml_path.exists():
        raise FileNotFoundError(f"GraphML file was not found: {graphml_path}")
    return nx.read_graphml(graphml_path)


def _safe_float(value, default=1.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _iter_incident_edges(graph, node_id):
    if graph.is_directed():
        yield from graph.out_edges(node_id, data=True)
        yield from graph.in_edges(node_id, data=True)
    else:
        yield from graph.edges(node_id, data=True)


def _weighted_degree(graph, node_id):
    return sum(
        _safe_float(edge_data.get("weight"), 1.0)
        for _, _, edge_data in _iter_incident_edges(graph, node_id)
    )


def _person_nodes(graph):
    return [
        node_id
        for node_id, attrs in graph.nodes(data=True)
        if str(attrs.get("entity_type", "")).lower() == "person"
    ]


def _pick_key_people(graph, top_n_people):
    people = _person_nodes(graph)
    if not people:
        raise ValueError("No person nodes were found in this graph.")

    ranked_people = sorted(
        people,
        key=lambda node_id: (
            _weighted_degree(graph, node_id),
            graph.degree(node_id),
            str(node_id).lower(),
        ),
        reverse=True,
    )
    return ranked_people[:top_n_people]


def _related_nodes_for_person(graph, person_id, limit):
    neighbor_scores = {}
    for source, target, edge_data in _iter_incident_edges(graph, person_id):
        other = target if source == person_id else source
        if other == person_id:
            continue

        entry = neighbor_scores.setdefault(other, {"weight": 0.0, "edge_count": 0})
        entry["weight"] += _safe_float(edge_data.get("weight"), 1.0)
        entry["edge_count"] += 1

    ranked_neighbors = sorted(
        neighbor_scores.items(),
        key=lambda item: (
            item[1]["weight"],
            item[1]["edge_count"],
            _weighted_degree(graph, item[0]),
            str(item[0]).lower(),
        ),
        reverse=True,
    )
    return [neighbor_id for neighbor_id, _ in ranked_neighbors[:limit]]


def _shorten_text(text, limit=140):
    text = str(text or "").replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def _build_key_person_subgraph(graph, top_n_people, max_related_nodes_per_person):
    key_people = _pick_key_people(graph, top_n_people)
    included_nodes = set(key_people)

    for person_id in key_people:
        included_nodes.update(
            _related_nodes_for_person(graph, person_id, max_related_nodes_per_person)
        )

    subgraph = graph.subgraph(included_nodes).copy()
    key_people_set = set(key_people)

    for node_id, attrs in subgraph.nodes(data=True):
        attrs["weighted_degree"] = round(_weighted_degree(graph, node_id), 2)
        attrs["is_key_person"] = node_id in key_people_set
        attrs["label_name"] = attrs.get("entity_id") or node_id
        attrs["label_type"] = attrs.get("entity_type", "unknown")
        attrs["short_description"] = _shorten_text(attrs.get("description", ""))

    return subgraph, key_people


def _key_person_graph_json(subgraph):
    nodes = []
    for node_id, attrs in subgraph.nodes(data=True):
        nodes.append(
            {
                "id": str(node_id),
                "label_name": str(attrs.get("label_name", node_id)),
                "entity_type": str(attrs.get("label_type", "unknown")),
                "description": str(attrs.get("description", "")),
                "short_description": str(attrs.get("short_description", "")),
                "weighted_degree": _safe_float(attrs.get("weighted_degree"), 0.0),
                "is_key_person": bool(attrs.get("is_key_person", False)),
            }
        )

    links = []
    for source, target, attrs in subgraph.edges(data=True):
        links.append(
            {
                "source": str(source),
                "target": str(target),
                "weight": _safe_float(attrs.get("weight"), 1.0),
                "description": str(attrs.get("description", "")),
                "keywords": str(attrs.get("keywords", "")),
            }
        )

    return json.dumps({"nodes": nodes, "links": links}, ensure_ascii=False).replace("</", "<\\/")


def _key_person_summary(subgraph, key_people):
    rows = []
    for person_id in key_people:
        attrs = subgraph.nodes[person_id]
        rows.append(
            {
                "person": attrs.get("label_name", person_id),
                "entity_type": attrs.get("label_type", "unknown"),
                "connection_score": _safe_float(attrs.get("weighted_degree"), 0.0),
                "visible_relations": subgraph.degree(person_id),
                "description": attrs.get("short_description", ""),
            }
        )

    return pd.DataFrame(rows)


def _save_key_person_html(
    html_path,
    dataset,
    graph_json,
    top_n_people,
    max_related_nodes_per_person,
):
    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Key Person Map</title>
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <style>
        * {{
            box-sizing: border-box;
        }}
        html, body {{
            margin: 0;
            width: 100%;
            height: 100%;
            overflow: hidden;
            font-family: "Segoe UI", sans-serif;
            background: #f5f3ee;
            color: #1f2937;
        }}
        .layout {{
            display: flex;
            width: 100%;
            height: 100%;
        }}
        .canvas {{
            position: relative;
            flex: 1;
            background:
                radial-gradient(circle at top left, rgba(190, 218, 255, 0.5), transparent 28%),
                linear-gradient(180deg, #fcfbf7 0%, #f4efe4 100%);
        }}
        svg {{
            width: 100%;
            height: 100%;
        }}
        .links line {{
            stroke: #7b8794;
            stroke-opacity: 0.35;
        }}
        .node circle {{
            stroke-width: 2px;
        }}
        .node-label text {{
            font-size: 12px;
            fill: #111827;
            pointer-events: none;
        }}
        .node-label .label-name {{
            font-weight: 700;
        }}
        .node-label .label-subtitle {{
            fill: #475569;
            font-size: 10px;
        }}
        .node-label rect {{
            fill: rgba(255, 255, 255, 0.82);
            stroke: rgba(148, 163, 184, 0.55);
            stroke-width: 1px;
            rx: 8px;
        }}
        .tooltip {{
            position: absolute;
            pointer-events: none;
            opacity: 0;
            padding: 10px 12px;
            max-width: 320px;
            background: rgba(15, 23, 42, 0.92);
            color: #f8fafc;
            border-radius: 10px;
            font-size: 12px;
            line-height: 1.5;
            transition: opacity 0.15s ease;
        }}
        .info-panel {{
            width: 320px;
            padding: 20px 18px;
            overflow-y: auto;
            border-left: 1px solid rgba(148, 163, 184, 0.35);
            background: #fffdf8;
        }}
        .panel-title {{
            margin: 0;
            font-size: 22px;
        }}
        .panel-subtitle {{
            margin: 8px 0 18px;
            color: #475569;
            font-size: 13px;
            line-height: 1.5;
        }}
        .panel-meta {{
            margin-bottom: 16px;
            padding: 12px;
            border-radius: 12px;
            background: #f3efe5;
            font-size: 13px;
            color: #334155;
            line-height: 1.6;
        }}
        .person-list {{
            display: grid;
            gap: 12px;
        }}
        .person-card {{
            padding: 12px;
            border-radius: 14px;
            background: #ffffff;
            border: 1px solid rgba(191, 219, 254, 0.95);
            box-shadow: 0 10px 24px rgba(15, 23, 42, 0.05);
        }}
        .person-name {{
            margin: 0 0 4px;
            font-size: 16px;
            font-weight: 700;
        }}
        .person-type {{
            margin: 0 0 8px;
            color: #475569;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.06em;
        }}
        .person-score {{
            margin: 0 0 8px;
            font-size: 12px;
            color: #0f766e;
            font-weight: 700;
        }}
        .person-description {{
            margin: 0;
            font-size: 13px;
            line-height: 1.6;
            color: #334155;
        }}
    </style>
</head>
<body>
    <div class="layout">
        <div class="canvas">
            <svg></svg>
            <div class="tooltip"></div>
        </div>
        <aside class="info-panel">
            <h1 class="panel-title">Key Person Map</h1>
            <p class="panel-subtitle">
                People are ranked by weighted connection score. Their strongest related entities are kept so names and basic context stay visible without hover.
            </p>
            <div class="panel-meta">
                <div><strong>Dataset:</strong> {dataset}</div>
                <div><strong>Key people:</strong> {top_n_people}</div>
                <div><strong>Related nodes per person:</strong> {max_related_nodes_per_person}</div>
            </div>
            <div class="person-list"></div>
        </aside>
    </div>
    <script>
        const graphData = {graph_json};

        const canvas = document.querySelector(".canvas");
        const width = canvas.clientWidth;
        const height = canvas.clientHeight;

        const svg = d3.select("svg").attr("viewBox", [0, 0, width, height]);
        const g = svg.append("g");
        const tooltip = d3.select(".tooltip");

        const entityTypes = [...new Set(graphData.nodes.map(node => node.entity_type))];
        const color = d3.scaleOrdinal(d3.schemeTableau10).domain(entityTypes);

        const simulation = d3.forceSimulation(graphData.nodes)
            .force("link", d3.forceLink(graphData.links).id(node => node.id).distance(link => link.source.is_key_person || link.target.is_key_person ? 120 : 80))
            .force("charge", d3.forceManyBody().strength(node => node.is_key_person ? -650 : -260))
            .force("center", d3.forceCenter(width / 2, height / 2))
            .force("collide", d3.forceCollide().radius(node => node.is_key_person ? 70 : 44))
            .force("radial", d3.forceRadial(node => node.is_key_person ? Math.min(width, height) * 0.18 : Math.min(width, height) * 0.28, width / 2, height / 2).strength(0.08));

        const link = g.append("g")
            .attr("class", "links")
            .selectAll("line")
            .data(graphData.links)
            .enter()
            .append("line")
            .attr("stroke-width", edge => Math.max(1.2, Math.sqrt(edge.weight || 1)));

        const node = g.append("g")
            .attr("class", "nodes")
            .selectAll("g")
            .data(graphData.nodes)
            .enter()
            .append("g")
            .attr("class", "node")
            .call(
                d3.drag()
                    .on("start", dragstarted)
                    .on("drag", dragged)
                    .on("end", dragended)
            );

        node.append("circle")
            .attr("r", d => d.is_key_person ? 12 : 7)
            .attr("fill", d => color(d.entity_type))
            .attr("stroke", d => d.is_key_person ? "#b45309" : "#ffffff");

        const label = g.append("g")
            .attr("class", "labels")
            .selectAll("g")
            .data(graphData.nodes)
            .enter()
            .append("g")
            .attr("class", "node-label");

        label.append("rect");

        label.append("text")
            .each(function(d) {{
                const text = d3.select(this);
                text.append("tspan")
                    .attr("class", "label-name")
                    .attr("x", 0)
                    .attr("dy", "0em")
                    .text(d.label_name);

                if (d.is_key_person) {{
                    text.append("tspan")
                        .attr("class", "label-subtitle")
                        .attr("x", 0)
                        .attr("dy", "1.25em")
                        .text(`${{d.entity_type}} | score ${{Number(d.weighted_degree).toFixed(1)}}`);
                }}
            }});

        label.each(function() {{
            const textBox = d3.select(this).select("text").node().getBBox();
            d3.select(this).select("rect")
                .attr("x", textBox.x - 6)
                .attr("y", textBox.y - 4)
                .attr("width", textBox.width + 12)
                .attr("height", textBox.height + 8);
        }});

        node.on("mouseover", function(event, d) {{
            tooltip
                .style("opacity", 1)
                .html(`
                    <strong>${{d.label_name}}</strong><br>
                    Type: ${{d.entity_type}}<br>
                    Score: ${{Number(d.weighted_degree).toFixed(1)}}<br><br>
                    ${{d.description || "No description"}}
                `)
                .style("left", `${{event.pageX + 12}}px`)
                .style("top", `${{event.pageY - 28}}px`);
        }}).on("mouseout", function() {{
            tooltip.style("opacity", 0);
        }});

        simulation.on("tick", () => {{
            link
                .attr("x1", edge => edge.source.x)
                .attr("y1", edge => edge.source.y)
                .attr("x2", edge => edge.target.x)
                .attr("y2", edge => edge.target.y);

            node.attr("transform", d => `translate(${{d.x}},${{d.y}})`);

            label.attr("transform", d => `translate(${{d.x + 16}},${{d.y - (d.is_key_person ? 18 : 10)}})`);
        }});

        const personList = d3.select(".person-list");
        graphData.nodes
            .filter(node => node.is_key_person)
            .sort((left, right) => d3.descending(left.weighted_degree, right.weighted_degree))
            .forEach(person => {{
                const card = personList.append("div").attr("class", "person-card");
                card.append("h2").attr("class", "person-name").text(person.label_name);
                card.append("p").attr("class", "person-type").text(person.entity_type);
                card.append("p").attr("class", "person-score").text(`Connection score: ${{Number(person.weighted_degree).toFixed(1)}}`);
                card.append("p").attr("class", "person-description").text(person.short_description || "No description");
            }});

        svg.call(
            d3.zoom()
                .scaleExtent([0.35, 4])
                .on("zoom", event => g.attr("transform", event.transform))
        );

        function dragstarted(event) {{
            if (!event.active) simulation.alphaTarget(0.3).restart();
            event.subject.fx = event.subject.x;
            event.subject.fy = event.subject.y;
        }}

        function dragged(event) {{
            event.subject.fx = event.x;
            event.subject.fy = event.y;
        }}

        function dragended(event) {{
            if (!event.active) simulation.alphaTarget(0);
            event.subject.fx = null;
            event.subject.fy = null;
        }}
    </script>
</body>
</html>
    """

    with open(html_path, "w", encoding="utf-8") as html_file:
        html_file.write(html_content)


def visualize_key_person_graph(
    dataset,
    html_path,
    top_n_people=8,
    max_related_nodes_per_person=5,
):
    graph = _load_graph(dataset)
    subgraph, key_people = _build_key_person_subgraph(
        graph,
        top_n_people=top_n_people,
        max_related_nodes_per_person=max_related_nodes_per_person,
    )

    html_dir = os.path.dirname(html_path)
    if html_dir and not os.path.exists(html_dir):
        os.makedirs(html_dir)

    _save_key_person_html(
        html_path=html_path,
        dataset=dataset,
        graph_json=_key_person_graph_json(subgraph),
        top_n_people=top_n_people,
        max_related_nodes_per_person=max_related_nodes_per_person,
    )

    return _key_person_summary(subgraph, key_people)
