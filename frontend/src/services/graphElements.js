const CLUSTER_COLORS = ['#2563eb', '#db2777', '#059669', '#d97706', '#7c3aed', '#0891b2', '#dc2626', '#475569'];
export const UNCLUSTERED_COLOR = '#94a3b8';

export function clusterColor(clusterId, clusters) {
  const index = clusters.findIndex((cluster) => cluster.cluster_id === clusterId);
  return index === -1 ? UNCLUSTERED_COLOR : CLUSTER_COLORS[index % CLUSTER_COLORS.length];
}

// Each platform gets a shape, in sorted order so the legend matches the graph.
// Shapes repeat if a dataset has more platforms than this list.
const PLATFORM_SHAPES = ['ellipse', 'round-rectangle', 'diamond', 'triangle', 'hexagon'];

export function platformShapes(nodes = []) {
  const platforms = [...new Set(nodes.map((node) => node.platform).filter(Boolean))].sort();
  return platforms.map((platform, index) => ({
    platform,
    shape: PLATFORM_SHAPES[index % PLATFORM_SHAPES.length],
  }));
}

// Splits accounts by whether any relationship touches them. If nothing is
// linked, everything stays visible so the canvas isn't blank.
export function hideUnlinked(graph) {
  const nodes = graph?.nodes ?? [];
  const linked = new Set((graph?.edges ?? []).flatMap((edge) => [edge.source, edge.target]));
  const visible = nodes.filter((node) => linked.has(node.id) || node.is_checked_post);
  if (linked.size === 0) return { graph, hiddenCount: 0 };
  return { graph: { ...graph, nodes: visible }, hiddenCount: nodes.length - visible.length };
}

// Converts the API graph into Cytoscape elements. Edges pointing at an unknown
// node are dropped and counted, because Cytoscape throws on them.
export function toElements(graph) {
  const clusters = graph?.clusters ?? [];
  const nodes = graph?.nodes ?? [];
  const ids = new Set(nodes.map((node) => node.id));
  const shapes = new Map(platformShapes(nodes).map(({ platform, shape }) => [platform, shape]));

  const nodeElements = nodes.map((node) => ({
    group: 'nodes',
    data: {
      id: node.id,
      label: node.label ?? node.id,
      platformShape: shapes.get(node.platform) ?? PLATFORM_SHAPES[0],
      color: clusterColor(node.cluster_id, clusters),
      checked: Boolean(node.is_checked_post),
      raw: node,
    },
  }));

  const valid = (graph?.edges ?? []).filter((edge) => ids.has(edge.source) && ids.has(edge.target));
  const edgeElements = valid.map((edge) => ({
    group: 'edges',
    data: {
      id: edge.id,
      source: edge.source,
      target: edge.target,
      width: 1 + (edge.signals?.length ?? 1),
      raw: edge,
    },
  }));

  return {
    elements: [...nodeElements, ...edgeElements],
    droppedEdges: (graph?.edges?.length ?? 0) - valid.length,
  };
}
