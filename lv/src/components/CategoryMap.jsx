/* Adapted from USAspending ExplorerTreemap (Kevin Li, 2017), CC0.
 * Keeps d3 hierarchy / binary treemap / TreemapCell composition; counts replace spending.
 */
import React, {useEffect, useRef, useState} from 'react';
import {hierarchy, treemap, treemapBinary} from 'd3-hierarchy';
import TreemapCell from './TreemapCell.jsx';
import {number} from '../data.js';
const colors = ['#782f3e', '#21584e', '#376e62', '#a4505b', '#477d71', '#7d6851', '#5e6250', '#536b7b'];
export default function CategoryMap({items, onSelect}) {
    const ref = useRef(null);
    const [width, setWidth] = useState(700);
    useEffect(() => {const observer = new ResizeObserver(([entry]) => setWidth(Math.max(280, entry.contentRect.width))); observer.observe(ref.current); return () => observer.disconnect();}, []);
    const selected = items.filter((i) => i.id !== '_none').slice(0, 8);
    const height = width < 450 ? 320 : 300;
    const root = hierarchy({children: selected}).sum((d) => d.amount || 0);
    const leaves = selected.length ? treemap().size([width, height]).tile(treemapBinary).paddingInner(5).round(true)(root).leaves() : [];
    return <div ref={ref} className="category-map">
        <svg width="100%" viewBox={`0 0 ${width} ${height}`} aria-label="Astoņas lielākās nozares pēc datu kopu skaita">
            {leaves.map((leaf, i) => {const w = leaf.x1 - leaf.x0, h = leaf.y1 - leaf.y0; const max = Math.max(5, Math.floor((w - 24) / 7)); const title = leaf.data.name.length > max ? leaf.data.name.slice(0, max - 1) + '…' : leaf.data.name;
                return <TreemapCell key={leaf.data.id} width={w} height={h} x={leaf.x0} y={leaf.y0} data={leaf.data} color={colors[i % colors.length]} title={{text: title, x: w / 2, y: h / 2 - 8}} subtitle={{text: `${number(leaf.data.amount)} kopas`, x: w / 2, y: h / 2 + 17}} selectedCell={onSelect} showTooltip={() => {}} hideTooltip={() => {}} goToUnreported={() => {}} />;})}
        </svg>
        <p className="caption">Laukums attēlo datu kopu skaitu. Viena kopa var būt vairākās nozarēs. Atlasiet laukumu, lai izpētītu datus.</p>
    </div>;
}
