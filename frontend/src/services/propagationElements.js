// Directed parent-to-child elements. This is not the coordination graph.

export function toPropagationElements(graph) {
  const nodes = graph?.nodes ?? [];
  const ids = new Set(nodes.map((node) => node.tweet_id));
  const nodeElements = nodes.map((node) => ({
    group: 'nodes',
    data: {
      id: node.tweet_id,
      label: node.is_root ? `root ${node.user_id}` : node.user_id,
      depth: node.depth ?? null,
      delay: node.post_time_delay_minutes ?? null,
      text: node.text ?? null,
      isRoot: Boolean(node.is_root),
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
      relationship: 'propagation_parent_to_child',
      parentDelay: edge.parent_delay_minutes ?? null,
      childDelay: edge.child_delay_minutes ?? null,
      raw: edge,
    },
  }));
  return {
    elements: [...nodeElements, ...edgeElements],
    droppedEdges: (graph?.edges?.length ?? 0) - valid.length,
    rootIds: nodes.filter((node) => node.is_root).map((node) => node.tweet_id),
  };
}

export function delayLabel(minutes) {
  if (typeof minutes !== 'number' || !Number.isFinite(minutes)) return 'Delay not recorded';
  return `${minutes} min from source`;
}
