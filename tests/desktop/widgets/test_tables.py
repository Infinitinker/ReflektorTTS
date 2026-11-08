from reflektortts.desktop.widgets.tables import _without_indicator


def test_a_flat_table_row_keeps_everything_but_the_expand_arrow() -> None:
    row = [
        (
            "Treeitem.padding",
            {
                "sticky": "nswe",
                "children": [
                    ("Treeitem.indicator", {"side": "left", "sticky": ""}),
                    ("Treeitem.image", {"side": "left", "sticky": ""}),
                    ("Treeitem.focus", {"children": [("Treeitem.text", {"sticky": "nswe"})]}),
                ],
            },
        )
    ]

    assert _without_indicator(row) == [
        (
            "Treeitem.padding",
            {
                "sticky": "nswe",
                "children": [
                    ("Treeitem.image", {"side": "left", "sticky": ""}),
                    ("Treeitem.focus", {"children": [("Treeitem.text", {"sticky": "nswe"})]}),
                ],
            },
        )
    ]
