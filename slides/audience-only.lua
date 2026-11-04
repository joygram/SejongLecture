-- Presenter notes remain in the authoring source and local workbench only.
function Div(el)
  if el.classes:includes('notes') then
    return {}
  end
end
